"""Faz 4 replay karşılaştırması (BİLGİLENDİRİCİ, kapı değil — ADR 0011): statik SL/TP vs kurallı yönetim.
Kullanım: python -m scripts.replay_positions data/recordings/<run> [--max-files N] [--sl 0.5] [--tp 1.0]
Giriş üreteci: Faz 3 durumları (S1 → long, S2 → short) bar kapanışında; aynı girişler iki konfigürasyona uygulanır.
Dolum: fbot/execution/sim.py (taker, karşı taraf best, sabit gecikme). Kayıtta tick yoksa recv_ns'ten deterministik tick sentezlenir.
Kârlılık gösterilmedi (ADR 0010); rapor yalnızca çıkış mekaniğini karşılaştırır."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from fbot.core.commands import BarClosed, PlaceAlgo, PlaceOrder
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PositionConfig, PosState
from fbot.events import RawEvent, decode
from fbot.execution.sim import SimConfig, SimExecutor
from fbot.replay.harness import iter_lines
from fbot.research.features import FeatureConfig, compute_features
from fbot.research.states import StateConfig, label_state

MS = 1_000_000
NOTIONAL = Decimal("80")


def load_filters(path="data/unit-economics/exchangeInfo.json") -> dict[str, Filters]:
    ex = json.load(open(path))
    out = {}
    for s in ex["symbols"]:
        f = {x["filterType"]: x for x in s["filters"]}
        out[s["symbol"]] = Filters(Decimal(f["LOT_SIZE"]["stepSize"]), Decimal(f["LOT_SIZE"]["minQty"]), Decimal(f["MIN_NOTIONAL"]["notional"]), Decimal(f["PRICE_FILTER"]["tickSize"]))
    return out


def pos_cfg(rules: bool) -> PositionConfig:
    base = dict(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True, min_replace_interval_ms=5000,
                taker_fee_pct=Decimal("0.05"), maker_fee_pct=Decimal("0.02"))
    if rules:
        base.update(max_hold_ms=3_600_000, lock_trigger_pct=Decimal("0.30"), lock_offset_pct=Decimal("0.05"),
                    trail_step_pct=Decimal("0.10"), trail_gap_pct=Decimal("0.30"), tp1_pct=None, tp1_frac=None)
    return PositionConfig(**base)


class Runner:
    def __init__(self, run_dir: Path, max_files, rules: bool, sl_pct: Decimal, tp_pct: Decimal, filters, W: int = 120):
        self.run_dir, self.max_files = run_dir, max_files
        self.cfg = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}, position=pos_cfg(rules), filters=filters, tick_ms=1000)
        self.engine, self.state = Engine(self.cfg), CoreState()
        self.sim = SimExecutor(SimConfig(latency_ms=400, seed=1))
        self.sl_pct, self.tp_pct = sl_pct, tp_pct
        self.bars: dict[str, list] = {}
        self.fcfg, self.scfg = FeatureConfig(W=W, N_short=5, N_long=15), StateConfig(0.2, 0.8)
        self.open_by_symbol: dict[str, str] = {}
        self.pending_entry: dict[str, tuple] = {}   # client_id → (pos_id, symbol, side)
        self.n_pos = 0
        self.records: dict[str, dict] = {}
        self.cmd_counts = Counter()
        self.seq = 0
        self.last_tick_ns = None
        self.had_ticks = False

    def _exec_event(self, kind: str, payload: dict, now_ns: int):
        self.seq += 1
        ev = RawEvent(self.seq, now_ns, self.seq, "exec", kind, json.dumps(payload).encode())
        self._step(ev)

    def _step(self, ev: RawEvent):
        self.state, cmds = self.engine.step(self.state, ev, ev.recv_ns)
        for c in cmds:
            self.cmd_counts[type(c).__name__] += 1
            if isinstance(c, (PlaceOrder, PlaceAlgo)) or type(c).__name__ == "CancelAlgo":
                self.sim.submit(c, ev.recv_ns)
                if isinstance(c, PlaceAlgo) and c.type == "STOP_MARKET" and not c.client_algo_id.endswith("-v1"):
                    self.records[c.client_algo_id.split("-SL-")[0]]["replacements"] += 1
            if isinstance(c, BarClosed):
                self._on_bar(c, ev.recv_ns)
        for e in self.sim.poll(ev.recv_ns):
            self._on_sim(e, ev.recv_ns)

    def _on_bar(self, b: BarClosed, now_ns: int):
        lst = self.bars.setdefault(b.symbol, [])
        lst.append({"symbol": b.symbol, "start_ms": b.start_ms, "end_ms": b.end_ms, "open": float(b.open), "high": float(b.high), "low": float(b.low),
                    "close": float(b.close), "volume": float(b.volume), "buy_volume": float(b.buy_volume), "trades": b.trades, "spread_bps": None})
        keep = self.fcfg.W + self.fcfg.N_long + 2
        if len(lst) > keep:
            del lst[:-keep]
        f = compute_features(lst, self.fcfg)[-1]
        st = label_state(f, self.scfg)
        self.state.market_state_label[b.symbol] = st
        if st in ("S1", "S2") and b.symbol not in self.open_by_symbol and b.symbol in self.cfg.filters:
            m = self.state.markets.get(b.symbol)
            if m is None or m.best_ask is None or m.mark_price is None:
                return
            filt = self.cfg.filters[b.symbol]
            qty = (NOTIONAL / m.best_ask // filt.step_size) * filt.step_size
            if qty < filt.min_qty or qty * m.best_ask < filt.min_notional:
                return
            self.n_pos += 1
            pid = f"p{self.n_pos}"
            side = "long" if st == "S1" else "short"
            cid = f"{pid}-E"
            self.pending_entry[cid] = (pid, b.symbol, side, st)
            self.open_by_symbol[b.symbol] = pid
            self.records[pid] = {"symbol": b.symbol, "side": side, "state": st, "replacements": 0, "max_net": Decimal("-999"), "net": None, "reason": None}
            self.sim.submit(PlaceOrder(b.symbol, "BUY" if side == "long" else "SELL", "MARKET", qty, None, False, cid, None), now_ns)

    def _on_sim(self, e: dict, now_ns: int):
        k = e["kind"]
        if k == "entry_fill_price":
            pid, sym, side, st = self.pending_entry.pop(e["client_id"])
            px = Decimal(e["price"])
            sl = px * (1 - self.sl_pct / 100) if side == "long" else px * (1 + self.sl_pct / 100)
            tp = px * (1 + self.tp_pct / 100) if side == "long" else px * (1 - self.tp_pct / 100)
            self.records[pid]["entry"] = px
            self._exec_event("entry_fill", {"pos_id": pid, "symbol": sym, "side": side, "price": str(px), "qty": e["qty"], "sl": str(sl), "tp": str(tp), "entry_state": st}, now_ns)
        elif k == "algo_ack":
            pid = e["client_algo_id"].split("-")[0]
            self._exec_event("algo_ack", {"pos_id": pid, "client_algo_id": e["client_algo_id"]}, now_ns)
        elif k == "algo_triggered":
            pid = e["client_algo_id"].split("-")[0]
            self._exec_event("algo_triggered", {"pos_id": pid, "client_algo_id": e["client_algo_id"]}, now_ns)
        elif k == "exit_fill":
            pid = e["client_id"].split("-")[0]
            pos = self.state.positions.get(pid)
            if pos is None or pos.state == PosState.CLOSED:
                return
            px = Decimal(e["price"])
            qty = pos.qty if e.get("qty") is None else Decimal(e["qty"])
            gross = (px / pos.entry_price - 1) * 100 if pos.side == "long" else (1 - px / pos.entry_price) * 100
            self._exec_event("exit_fill", {"pos_id": pid, "price": str(px), "qty": str(qty), "reason": e.get("reason")}, now_ns)
            if self.state.positions[pid].state == PosState.CLOSED:
                r = self.records[pid]
                r["net"] = gross - Decimal("0.10")
                r["reason"] = self.state.positions[pid].exit_reason
                self.open_by_symbol.pop(r["symbol"], None)

    def run(self):
        pm = self.engine.pm
        for line in iter_lines(self.run_dir, self.max_files):
            ev = decode(line)
            if ev.cat == "ctrl" and ev.stream == "tick":
                self.had_ticks = True
            if not self.had_ticks:
                if self.last_tick_ns is None:
                    self.last_tick_ns = ev.recv_ns
                while ev.recv_ns - self.last_tick_ns >= self.cfg.tick_ms * MS:
                    self.last_tick_ns += self.cfg.tick_ms * MS
                    self.seq += 1
                    self._step(RawEvent(self.seq, self.last_tick_ns, self.seq, "ctrl", "tick", b'{"synthetic":1}'))
            self.seq = max(self.seq, ev.seq)
            self._step(ev)
            if ev.cat != "ctrl":
                d = self.state.last_data or {}
                if d.get("e") == "bookTicker":
                    self.sim.on_book(d["s"], Decimal(d["b"]), Decimal(d["a"]), ev.recv_ns)
                elif d.get("e") == "markPriceUpdate":
                    for e in self.sim.on_mark(d["s"], Decimal(d["p"]), ev.recv_ns):
                        self._on_sim(e, ev.recv_ns)
                    for pid, pos in self.state.positions.items():
                        if pos.symbol == d["s"] and pos.state in (PosState.MANAGED, PosState.PROTECTING) and pos.entry_price:
                            net = pm.net_unrealized_pct(pos, Decimal(d["p"]))
                            if net > self.records[pid]["max_net"]:
                                self.records[pid]["max_net"] = net
        return self.summary()

    def summary(self) -> dict:
        closed = [r for r in self.records.values() if r["net"] is not None]
        n = len(closed)
        if n == 0:
            return {"positions": 0}
        nets = [r["net"] for r in closed]
        was_profit = [r for r in closed if r["max_net"] > Decimal("0.10")]
        p2l = [r for r in was_profit if r["net"] < 0]
        return {
            "positions": n, "open_at_end": len(self.records) - n,
            "net_mean_pct": float(sum(nets) / n), "win_rate": sum(1 for x in nets if x > 0) / n,
            "net_sum_pct": float(sum(nets)),
            "profit_to_loss_rate": (len(p2l) / len(was_profit)) if was_profit else None, "was_profit": len(was_profit),
            "exit_reasons": dict(Counter(r["reason"] for r in closed)),
            "replacements": sum(r["replacements"] for r in self.records.values()),
            "commands": dict(self.cmd_counts), "synthetic_ticks": not self.had_ticks,
        }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--sl", default="0.5")
    ap.add_argument("--tp", default="1.0")
    ap.add_argument("--W", type=int, default=120, help="persentil penceresi (bar); kısa kayıtta 120")
    a = ap.parse_args(argv)
    filters = load_filters()
    res = {}
    for name, rules in (("statik SL/TP", False), ("statik + R1/R3/R5", True)):
        res[name] = Runner(Path(a.run_dir), a.max_files, rules, Decimal(a.sl), Decimal(a.tp), filters, a.W).run()
    print(f"# Faz 4 replay karşılaştırması — `{Path(a.run_dir).name}` (SL {a.sl}%, TP {a.tp}%, W={a.W}, giriş S1 long / S2 short, 80 USDT, taker/taker)\n")
    print("Kârlılık gösterilmedi (ADR 0010). Bilgilendirici karşılaştırma (ADR 0011).\n")
    keys = ["positions", "open_at_end", "net_mean_pct", "net_sum_pct", "win_rate", "was_profit", "profit_to_loss_rate", "replacements", "exit_reasons", "commands", "synthetic_ticks"]
    print("| ölçüt | " + " | ".join(res) + " |")
    print("|---|" + "---|" * len(res))
    for k in keys:
        print(f"| {k} | " + " | ".join(str(res[n].get(k)) for n in res) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
