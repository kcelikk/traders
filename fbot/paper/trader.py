"""Paper trader (Faz 7): canlı akış → saf çekirdek → simüle execution.

Rule Zero: simülatörün ürettiği her sonuç (`entry_fill`, `algo_ack`, `algo_triggered`, `exit_fill`) ve
çekirdeğin ürettiği her komut **aynı sıralı akışa** olay olarak yazılır. Böylece kaydın replay'i,
canlı koşunun karar/emir dizisini bit-eşit üretir (sim yeniden çalıştırılmaz).

Gerçek emir yolu yoktur: `LiveExecutionAdapter` korumalı stub'dır (CLAUDE.md). Kârlılık gösterilmedi (ADR 0010).
"""
from __future__ import annotations

import json
from decimal import Decimal

from fbot.core.commands import CancelAlgo, CancelOrder, PlaceAlgo, PlaceOrder, StateChanged, canonical
from fbot.core.engine import CoreState
from fbot.events import RawEvent

ORDER_CMDS = (PlaceOrder, PlaceAlgo, CancelAlgo, CancelOrder)


def _cmd_payload(c) -> dict:
    """Komut adı `cmd` anahtarında: emrin kendi `type` alanıyla (MARKET/STOP_MARKET) çakışmasın."""
    d = {"cmd": type(c).__name__}
    for k, v in ((f, getattr(c, f)) for f in c.__slots__):
        d[k] = str(v) if isinstance(v, Decimal) else v
    return d


class PaperTrader:
    def __init__(self, engine, sim, emit, state: CoreState | None = None):
        self.engine = engine
        self.sim = sim
        self.emit = emit                    # (cat, stream, raw[, recv_ns, mono_ns]) -> RawEvent
        self.engine_state = state or CoreState()
        self.commands: list = []            # canlı koşunun komut dizisi (replay ile karşılaştırılır)
        self.stats = {"orders": 0, "fills": 0, "algos": 0, "cancels": 0, "state_changes": 0, "rejects": 0}

    # ---------------- akış
    def on_event(self, ev: RawEvent, now_ns: int) -> None:
        """Kayda yazılmış (sıralanmış) bir olayı çekirdeğe verir ve sonuçları işler."""
        self._step(ev, now_ns)
        self._feed_sim_from(ev, now_ns)
        self._drain_sim(now_ns)

    def on_tick(self, now_ns: int) -> None:
        """Periyodik tick: kurallar (R1/R3/R5) ve simülatör kuyruğu."""
        ev = self.emit("ctrl", "tick", b'{"src":"paper"}', now_ns, now_ns)
        self._step(ev, now_ns)
        self._drain_sim(now_ns)

    # ---------------- iç
    def _step(self, ev: RawEvent, now_ns: int) -> None:
        self.engine_state, cmds = self.engine.step(self.engine_state, ev, now_ns)
        for c in cmds:
            self.commands.append(c)
            if isinstance(c, StateChanged):
                self.stats["state_changes"] += 1
                self.emit("ctrl", "state_changed", json.dumps({"symbol": c.symbol, "from_state": c.from_state, "to_state": c.to_state,
                                                               "bar_end_ms": c.bar_end_ms, "confidence": c.confidence,
                                                               "evidence": c.evidence, "counter": c.counter}, separators=(",", ":")).encode(), now_ns, now_ns)
            elif isinstance(c, ORDER_CMDS):
                self.emit("ctrl", "command", json.dumps(_cmd_payload(c), separators=(",", ":")).encode(), now_ns, now_ns)
                self.sim.submit(c, now_ns)
                if isinstance(c, PlaceOrder):
                    self.stats["orders"] += 1
                elif isinstance(c, PlaceAlgo):
                    self.stats["algos"] += 1
                else:
                    self.stats["cancels"] += 1
        rej = self.engine_state.intents_rejected
        self.stats["rejects"] = rej

    def _feed_sim_from(self, ev: RawEvent, now_ns: int) -> None:
        d = self.engine_state.last_data
        if ev.cat == "ctrl" or not d:
            return
        e = d.get("e")
        if e == "bookTicker":
            self.sim.on_book(d["s"], Decimal(d["b"]), Decimal(d["a"]), now_ns)
        elif e == "markPriceUpdate":
            for out in self.sim.on_mark(d["s"], Decimal(d["p"]), now_ns):
                self._emit_exec(out, now_ns)

    def _drain_sim(self, now_ns: int) -> None:
        for out in self.sim.poll(now_ns):
            self._emit_exec(out, now_ns)

    def _emit_exec(self, out: dict, now_ns: int) -> None:
        """Simülatör sonucunu exec olayına çevirip akışa yazar, sonra çekirdeğe verir."""
        kind = out["kind"]
        payload = None
        if kind == "entry_fill_price":
            payload, kind = {"client_id": out["client_id"], "symbol": out["symbol"], "price": out["price"], "qty": out["qty"], "is_maker": False}, "entry_fill"
            self.stats["fills"] += 1
        elif kind in ("algo_ack", "algo_triggered"):
            cid = out["client_algo_id"]
            payload = {"pos_id": cid.split("-")[0], "client_algo_id": cid}
        elif kind == "exit_fill":
            pos_id = out["client_id"].split("-")[0]
            pos = self.engine_state.positions.get(pos_id)
            qty = out.get("qty") or (str(pos.qty) if pos else None)
            if qty is None:
                return
            payload = {"pos_id": pos_id, "price": out["price"], "qty": qty, "reason": out.get("reason")}
            self.stats["fills"] += 1
        if payload is None:
            return
        ev = self.emit("exec", kind, json.dumps(payload, separators=(",", ":")).encode(), now_ns, now_ns)
        self._step(ev, now_ns)
