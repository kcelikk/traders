"""Testnet trading process (Faz 9, ADR 0015): canlı testnet verisi + saf çekirdek + GERÇEK testnet emirleri.

Paper'dan tek farkı execution adapter'ı: simülatör yerine `TestnetAdapter` (REST + HMAC, yalnızca
testnet.binancefuture.com). Kayıt, sıralama ve determinizm aynı; emir cevapları da aynı akışa yazılır.

Silahlanma (hepsi gerekli): FBOT_TESTNET_ARMED · .env anahtar çifti · config [mode].mode = "testnet".
Biri eksikse süreç emir göndermez, nedenini yazar ve yalnızca kayıt/analiz yapar.
Testnet sonuçları kârlılık kanıtı değildir.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import tomllib
from decimal import Decimal
from pathlib import Path

from fbot.core.engine import Engine
from fbot.core.order_state import OrderBook as OrderTracker
from fbot.execution.testnet_adapter import TestnetAdapter, TestnetDisarmed
from fbot.gateway.killswitch import KillSwitch
from fbot.gateway.testnet import TestnetClient, TestnetError
from fbot.gateway.credfile import testnet_paths
from fbot.testnet.arming import ArmingSupervisor
from fbot.paper.config import load_paper_config
from fbot.paper.main import PaperRecorder, filters_from_exchange_info
from fbot.paper.config_view import effective_config
from fbot.paper.store import PaperStore
from fbot.paper.trader import ORDER_CMDS, PaperTrader, _cmd_payload
from fbot.recorder.main import git_sha

ROOT = Path(__file__).resolve().parents[2]


class TestnetTrader(PaperTrader):
    """PaperTrader'ın execution'ı değişmiş hâli: komutlar simülatöre değil testnet'e gider."""

    def __init__(self, engine, adapter: TestnetAdapter, emit, store=None):
        super().__init__(engine, sim=_NullSim(), emit=emit, store=store)
        self.adapter = adapter
        self.orders = OrderTracker()
        self.errors = {"rejected": 0, "unknown": 0, "failed": 0}

    def _step(self, ev, now_ns: int) -> None:
        self.engine_state, cmds = self.engine.step(self.engine_state, ev, now_ns)
        for c in cmds:
            self.commands.append(c)
            if type(c).__name__ == "StateChanged":
                self.stats["state_changes"] += 1
                self.emit("ctrl", "state_changed", json.dumps({"symbol": c.symbol, "from_state": c.from_state,
                                                               "to_state": c.to_state, "bar_end_ms": c.bar_end_ms,
                                                               "confidence": c.confidence, "evidence": c.evidence,
                                                               "counter": c.counter}, separators=(",", ":")).encode(), now_ns, now_ns)
            elif isinstance(c, ORDER_CMDS):
                self._send(c, now_ns)
        self.stats["rejects"] = self.engine_state.intents_rejected
        self._record_verdicts()
        self._record_positions()

    def _send(self, c, now_ns: int) -> None:
        payload = _cmd_payload(c)
        cev = self.emit("ctrl", "command", json.dumps(payload, separators=(",", ":")).encode(), now_ns, now_ns)
        if self.store is not None:
            self.store.record_order({**payload, "seq": cev.seq, "t_ns": now_ns})
        try:
            out = self.adapter.submit(c, now_ms=now_ns // 1_000_000)
        except TestnetDisarmed as e:
            self.emit("ctrl", "order_skipped", json.dumps({"reason": str(e), "cmd": payload["cmd"]}, separators=(",", ":")).encode(), now_ns, now_ns)
            return
        except TestnetError as e:
            self.errors["failed"] += 1
            self.emit("ctrl", "order_failed", json.dumps({"status": e.status, "code": e.code, "msg": str(e)[:200],
                                                          "cmd": payload["cmd"]}, separators=(",", ":")).encode(), now_ns, now_ns)
            return
        kind = out.get("kind", "")
        if kind.endswith("_rejected"):
            self.errors["rejected"] += 1
        elif kind.endswith("_unknown"):
            self.errors["unknown"] += 1
        if kind.startswith("order"):
            self.stats["orders"] += 1
        elif kind.startswith("algo"):
            self.stats["algos"] += 1
        self.emit("exec", kind, json.dumps(out, separators=(",", ":"), default=str).encode(), now_ns, now_ns)

    def on_user_event(self, mapped: dict, now_ns: int) -> None:
        """User data akışından gelen olay: emir durumu güncellenir, çekirdeğe exec olayı olarak verilir."""
        kind = mapped.get("kind")
        if kind in ("order_fill", "order_ack", "order_done"):
            self.orders.apply({**mapped, "trade_id": mapped.get("trade_id")})
        ev = self.emit("exec", kind, json.dumps(mapped, separators=(",", ":"), default=str).encode(), now_ns, now_ns)
        super()._step(ev, now_ns) if False else self._step(ev, now_ns)


class _NullSim:
    """Testnet'te simülatör yok; PaperTrader'ın çağrılarını yutar."""
    pending_orders: list = []
    triggered: list = []

    def on_depth(self, *a, **k): pass
    def on_book(self, *a, **k): pass
    def on_mark(self, *a, **k): return []
    def poll(self, *a, **k): return []
    def submit(self, *a, **k): pass
    def set_position(self, *a, **k): pass


class TestnetRecorder(PaperRecorder):
    async def resolve_universe(self):
        syms = await asyncio.to_thread(lambda: list(self.pcfg.recorder.symbols))
        from fbot.gateway.rest import exchange_info
        ex = await asyncio.to_thread(exchange_info)
        core = self.pcfg.core
        core = type(core)(**{**core.__dict__, "filters": filters_from_exchange_info(ex, set(syms))})
        prec = {s["symbol"]: {"pricePrecision": s["pricePrecision"], "quantityPrecision": s["quantityPrecision"]}
                for s in ex["symbols"] if s["symbol"] in set(syms)}
        # Adapter silahsız doğar; anahtar dosyasını denetçi okur ve gerekirse çalışırken silahlandırır
        adapter = TestnetAdapter(None, armed=False, symbols=prec)
        self.trader = TestnetTrader(Engine(core), adapter,
                                    lambda cat, stream, raw, recv_ns=None, mono_ns=None: self.emit(cat, stream, raw, recv_ns, mono_ns, notify=False),
                                    store=self.store)
        self.arming = ArmingSupervisor(
            env_path=testnet_paths(ROOT), adapter=adapter,
            make_client=lambda creds: TestnetClient(creds, reserve_orders=self.pcfg.core.risk.reserve_orders),
            probe=self._probe_balance,
            open_positions=lambda: sum(1 for p in self.trader.engine_state.positions.values() if p.state.value != "CLOSED"))
        ev = self.arming.check()
        armed, why = adapter.armed, (ev or {}).get("reason", "—")
        if ev:
            self._emit_arming(ev)
        if self.pcfg.cost_drift is not None:
            from fbot.core.cost_drift import CostDriftMonitor
            self.trader.drift = CostDriftMonitor(self.pcfg.cost_drift)
        self.trader.engine_state.kill_switch = self.kill.active
        self.ctrl("testnet_start", {"armed": armed, "why": why, "symbols": syms,
                                    "cells": [c.key() for c in core.decision.allowed_cells],
                                    "note": "testnet tesisat doğrulama ortamıdır; kârlılık kanıtı değildir (ADR 0015)"}, notify=False)
        return syms

    def _probe_balance(self, client) -> float:
        """Silahlanma kanıtı: yeni anahtarla bakiye okunabiliyor mu? Hesap görünümünü de günceller."""
        bal = client.balance(int(time.time() * 1000))
        usdt = next((float(b["balance"]) for b in bal if b.get("asset") == "USDT"), 0.0)
        self.pcfg.core.account["available_balance"] = str(usdt)
        return usdt

    def _emit_arming(self, ev: dict) -> None:
        """Silahlanma değişikliğini kayda ve konsola yazar. Gizli anahtar yazılmaz (yalnızca maske)."""
        self._arming_reason = ev.get("reason")
        self.ctrl(ev["kind"], ev, notify=False)
        print(json.dumps({"msg": ev["kind"], **ev}, ensure_ascii=False), flush=True)

    def _beat(self, kill: bool) -> None:
        """Periyodik durum görevi: önce anahtar dosyasını denetle, sonra canlılık damgasını bas."""
        try:
            ev = self.arming.check()
            if ev:
                self._emit_arming(ev)
        except Exception as e:  # noqa: BLE001 — denetçi hatası kaydı durdurmaz
            print(json.dumps({"msg": "arming_error", "err": repr(e)}), flush=True)
        st = self.trader.engine_state
        self.store.heartbeat(now_ns=time.time_ns(),
                             detail={"kill_switch": kill, "positions": len(st.positions), "stats": dict(self.trader.stats),
                                     "open": sum(1 for p in st.positions.values() if p.state.value != "CLOSED"),
                                     "armed": self.trader.adapter.armed,
                                     "arming_reason": getattr(self, "_arming_reason", None),
                                     # Konsolun "sistem bağlantı durumu" tablosu bunları okur
                                     "orders": len(self.trader.orders.orders),
                                     "fills": self.trader.orders._stats["fills"],
                                     "rejected": self.trader.errors["rejected"],
                                     "reconciled": None})


def parse(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/testnet.toml")
    p.add_argument("--run-id", default=os.environ.get("FBOT_RUN_ID"))
    p.add_argument("--duration", type=float, default=None)
    return p.parse_args(argv)


def main(argv):
    a = parse(argv)
    cfg, h = load_paper_config(a.config)
    mode = tomllib.loads(Path(a.config).read_bytes().decode()).get("mode", {}).get("mode")
    if mode != "testnet":
        raise SystemExit(f"config [mode].mode 'testnet' değil ({mode}): testnet süreci başlatılmaz")
    run_id = a.run_id or time.strftime("testnet-%Y%m%dT%H%M%SZ", time.gmtime())
    db = Path(cfg.recorder.out_dir) / run_id / "paper.db"
    store = PaperStore(db, run_id=run_id, env="testnet")
    store.set_config({"config_path": a.config, "git_sha": git_sha(), **effective_config(cfg)}, config_hash=h)
    print(json.dumps({"msg": "testnet start", "run_id": run_id, "config_hash": h, "git_sha": git_sha(),
                      "armed_env": bool(os.environ.get("FBOT_TESTNET_ARMED")),
                      "hot_reload": "anahtar .env'den 10 s'de bir okunur; yeniden başlatma gerekmez",
                      "note": "yalnızca testnet.binancefuture.com; kârlılık kanıtı değildir"}), flush=True)
    asyncio.run(TestnetRecorder(cfg, h, run_id, a.duration, store).main())
    print(json.dumps({"msg": "testnet stop", "summary": store.summary()}, default=str), flush=True)
    store.close()


if __name__ == "__main__":
    main(sys.argv[1:])
