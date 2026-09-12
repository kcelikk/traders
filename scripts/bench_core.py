"""`Engine.step` mikro-ölçümü: olay tipi başına işleme süresi. Salt okunur, üretim koduna dokunmaz.

Kullanım: python -m scripts.bench_core [--fixture tests/fixtures/rec-mini] [--json-out data/bench/<sha>.json]

Neden gerekiyor: bugüne kadar `events_per_s` ölçülüyordu ama eşiklenmiyordu; sıcak yolu
değiştiren her refactor'ün öncesi/sonrası karşılaştırılabilir olmalı.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.events import decode
from fbot.replay.harness import iter_lines
from scripts.latency_core import percentiles

CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000})


def kind_of(stream: str) -> str:
    return stream.split("@")[-1] if "@" in stream else stream


def bench(fixture: Path, max_files: int | None = None) -> dict:
    engine, state = Engine(CFG), CoreState()
    by: dict[str, list] = defaultdict(list)
    n = 0
    t0 = time.perf_counter()
    for line in iter_lines(fixture, max_files):
        ev = decode(line)
        s0 = time.perf_counter_ns()
        state, _ = engine.step(state, ev, ev.recv_ns)
        by[kind_of(ev.stream)].append(time.perf_counter_ns() - s0)
        n += 1
    elapsed = time.perf_counter() - t0
    out = {"fixture": str(fixture), "events": n, "elapsed_s": round(elapsed, 4),
           "events_per_s": round(n / elapsed, 1) if elapsed else None, "by_kind": {}}
    for k, v in by.items():
        p = percentiles([x / 1000 for x in v])      # µs
        out["by_kind"][k] = {"n": len(v), "p50_us": round(p["p50"], 2), "p95_us": round(p["p95"], 2),
                             "p99_us": round(p["p99"], 2), "max_us": round(max(v) / 1000, 2)}
    allv = [x / 1000 for v in by.values() for x in v]
    p = percentiles(allv)
    out["overall"] = {"p50_us": round(p["p50"], 2), "p95_us": round(p["p95"], 2),
                      "p99_us": round(p["p99"], 2), "max_us": round(max(allv), 2)}
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="tests/fixtures/rec-mini")
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args(argv)
    r = bench(Path(a.fixture), a.max_files)
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(r, indent=1))
    print(f"# Engine.step · {r['events']} olay · {r['events_per_s']:,.0f} olay/s")
    print(f"{'olay tipi':14s} {'adet':>8s} {'p50 µs':>8s} {'p95 µs':>8s} {'p99 µs':>8s} {'maks µs':>9s}")
    for k in sorted(r["by_kind"], key=lambda x: -r["by_kind"][x]["n"]):
        d = r["by_kind"][k]
        print(f"{k:14s} {d['n']:8d} {d['p50_us']:8.2f} {d['p95_us']:8.2f} {d['p99_us']:8.2f} {d['max_us']:9.2f}")
    o = r["overall"]
    print(f"{'TOPLAM':14s} {r['events']:8d} {o['p50_us']:8.2f} {o['p95_us']:8.2f} {o['p99_us']:8.2f} {o['max_us']:9.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
