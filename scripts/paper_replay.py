"""Paper yığınını kayıt üzerinde hızlı koşturur (canlı ile aynı kod yolu: PaperTrader + Engine + config).
Kullanım: python -m scripts.paper_replay data/recordings/<run> --config config/paper-demo.toml [--max-files N]

Canlı paper ile fark: WS yerine kayıt, duvar saati yerine olay zamanı. Çıktı: özet + opsiyonel SQLite.
Kârlılık gösterilmedi (ADR 0010)."""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from fbot.core.engine import Engine
from fbot.core.position import Filters
from fbot.events import RawEvent, decode
from fbot.execution.sim import SimConfig, SimExecutor
from fbot.paper.config import load_paper_config
from fbot.paper.store import PaperStore
from fbot.paper.trader import PaperTrader
from fbot.replay.harness import iter_lines
from fbot.sequencer import Sequencer


def load_filters(path="data/unit-economics/exchangeInfo.json") -> dict[str, Filters]:
    ex = json.load(open(path))
    out = {}
    for s in ex["symbols"]:
        f = {x["filterType"]: x for x in s["filters"]}
        if "LOT_SIZE" in f and "MIN_NOTIONAL" in f and "PRICE_FILTER" in f:
            out[s["symbol"]] = Filters(Decimal(f["LOT_SIZE"]["stepSize"]), Decimal(f["LOT_SIZE"]["minQty"]),
                                       Decimal(f["MIN_NOTIONAL"]["notional"]), Decimal(f["PRICE_FILTER"]["tickSize"]))
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--config", default="config/paper.toml")
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg, h = load_paper_config(a.config)
    core = type(cfg.core)(**{**cfg.core.__dict__, "filters": load_filters()})
    store = PaperStore(Path(a.db), run_id=Path(a.run_dir).name) if a.db else None
    seq = Sequencer()
    out_stream: list[RawEvent] = []

    def emit(cat, stream, raw, recv_ns=None, mono_ns=None):
        ev = seq.next(recv_ns or 0, mono_ns or 0, cat, stream, raw)
        out_stream.append(ev)
        return ev

    trader = PaperTrader(Engine(core), SimExecutor(SimConfig(latency_ms=cfg.sim_latency_ms, seed=cfg.sim_seed)), emit, store=store)
    n = 0
    last_tick = None
    for line in iter_lines(Path(a.run_dir), a.max_files):
        ev = decode(line)
        seq.last_seq = max(seq.last_seq, ev.seq)
        if last_tick is None:
            last_tick = ev.recv_ns
        while ev.recv_ns - last_tick >= core.tick_ms * 1_000_000:
            last_tick += core.tick_ms * 1_000_000
            trader.on_tick(last_tick)
        trader.on_event(ev, ev.recv_ns)
        n += 1
    st = trader.engine_state
    summary = {"events": n, "emitted": len(out_stream), **trader.stats, "intents": st.intents_made, "rejected": st.intents_rejected,
               "positions": len(st.positions), "closed": sum(1 for p in st.positions.values() if p.state.value == "CLOSED"),
               "cells": [c.key() for c in core.decision.allowed_cells], "config_hash": h}
    if store is not None:
        store.flush()
        summary["store"] = store.summary()
        store.close()
    print(json.dumps(summary, default=str, indent=None if a.json else 1))


if __name__ == "__main__":
    main(sys.argv[1:])
