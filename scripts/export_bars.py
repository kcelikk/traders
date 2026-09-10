"""Replay → bar serisi (JSONL). Her BarClosed'a kapanış anındaki spread, mark, index, funding eklenir.
Kullanım: python -m scripts.export_bars data/recordings/<run> data/research/<run>/bars.jsonl [--max-files N]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fbot.clock import ReplayClock
from fbot.core.commands import BarClosed
from fbot.core.engine import CoreState, Engine
from fbot.events import decode
from fbot.replay.harness import DEFAULT_CFG, iter_lines


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("out")
    ap.add_argument("--max-files", type=int, default=None)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    engine, state, clock = Engine(DEFAULT_CFG), CoreState(), ReplayClock()
    n = nb = 0
    with out.open("w") as f:
        for line in iter_lines(Path(a.run_dir), a.max_files):
            ev = decode(line)
            clock.set(ev.recv_ns)
            state, cmds = engine.step(state, ev, clock.now_ns())
            n += 1
            for c in cmds:
                if not isinstance(c, BarClosed):
                    continue
                m = state.markets[c.symbol]
                spread = None
                if m.best_bid is not None and m.best_ask is not None and m.best_ask > 0:
                    spread = float((m.best_ask - m.best_bid) / m.best_ask * 10000)
                f.write(json.dumps({
                    "symbol": c.symbol, "start_ms": c.start_ms, "end_ms": c.end_ms,
                    "open": float(c.open), "high": float(c.high), "low": float(c.low), "close": float(c.close),
                    "volume": float(c.volume), "buy_volume": float(c.buy_volume), "trades": c.trades,
                    "spread_bps": spread,
                    "mark": float(m.mark_price) if m.mark_price is not None else None,
                    "index": float(m.index_price) if m.index_price is not None else None,
                    "funding_rate": float(m.funding_rate) if m.funding_rate is not None else None,
                    "next_funding_ms": m.next_funding_ms,
                }, separators=(",", ":")) + "\n")
                nb += 1
    print(json.dumps({"events": n, "bars": nb, "out": str(out)}))


if __name__ == "__main__":
    main(sys.argv[1:])
