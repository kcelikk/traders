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
from fbot.core.position import Filters, PositionConfig
from fbot.core.reactors import ReactorConfig
from fbot.events import decode
from fbot.replay.harness import iter_lines
from scripts.latency_core import percentiles

CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000})

# Reactor bütçesi (Gate 4): açık pozisyon varken `bookTicker` dalında +%20'yi aşmamalı.
# Ölçüm gerçek pozisyonla yapılır; boş `by_symbol` ile reactor O(1) döner ve hiçbir şey ölçülmez.
_D = __import__("decimal").Decimal
BENCH_SYMBOL = "BTCUSDT"
_PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                       min_replace_interval_ms=5000, taker_fee_pct=_D("0.05"), maker_fee_pct=_D("0.02"))
_FILT = {BENCH_SYMBOL: Filters(_D("0.001"), _D("0.001"), _D("5"), _D("0.10"))}


def reactor_cfg(mode: str) -> CoreConfig:
    return CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000},
                      position=_PCFG, filters=_FILT,
                      reactors=ReactorConfig(mode=mode, enabled=("backup_stop",) if mode != "off" else ()))


def seed_position(engine, state):
    """Reaktörün çalışması için bir açık pozisyon. Stop **piyasanın üstünde** seçilir: her olayda
    niyet üretilir, yani ölçülen şey en kötü durumdur (bütçe böyle test edilmeli)."""
    fill = json.dumps({"pos_id": "b0Lbench", "symbol": BENCH_SYMBOL, "side": "long", "price": "77000",
                       "qty": "0.001", "sl": "999999", "tp": "1000000"}).encode()
    from fbot.events import RawEvent
    state, _ = engine.step(state, RawEvent(0, 1, 1, "exec", "entry_fill", fill), 1)
    state.positions["b0Lbench"].state = __import__("fbot.core.position", fromlist=["PosState"]).PosState.MANAGED
    return state


def kind_of(stream: str) -> str:
    return stream.split("@")[-1] if "@" in stream else stream


def bench(fixture: Path, max_files: int | None = None, cfg: CoreConfig = CFG, seed: bool = False) -> dict:
    engine, state = Engine(cfg), CoreState()
    if seed:
        state = seed_position(engine, state)
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
    shadow = getattr(state, "shadow_intents", 0)
    out = {"fixture": str(fixture), "events": n, "elapsed_s": round(elapsed, 4),
           "events_per_s": round(n / elapsed, 1) if elapsed else None, "shadow_intents": shadow, "by_kind": {}}
    for k, v in by.items():
        p = percentiles([x / 1000 for x in v])      # µs
        out["by_kind"][k] = {"n": len(v), "p50_us": round(p["p50"], 2), "p95_us": round(p["p95"], 2),
                             "p99_us": round(p["p99"], 2), "max_us": round(max(v) / 1000, 2)}
    allv = [x / 1000 for v in by.values() for x in v]
    p = percentiles(allv)
    out["overall"] = {"p50_us": round(p["p50"], 2), "p95_us": round(p["p95"], 2),
                      "p99_us": round(p["p99"], 2), "max_us": round(max(allv), 2)}
    return out


def _reactor_report(fixture: Path, max_files: int | None) -> int:   # noqa: C901
    """Aynı fixture, açık pozisyonlu iki koşu: reactor kapalı ve shadow. Bütçe `bookTicker` dalında."""
    off = bench(fixture, max_files, cfg=reactor_cfg("off"), seed=True)
    sh = bench(fixture, max_files, cfg=reactor_cfg("shadow"), seed=True)
    print(f"{'dal':14s} {'kapalı p50':>11s} {'shadow p50':>11s} {'kapalı p99':>11s} {'shadow p99':>11s} {'p50 fark':>9s}")
    for k in ("bookTicker", "1s", "aggTrade"):
        o, n = off["by_kind"].get(k), sh["by_kind"].get(k)
        if not o or not n:
            continue
        delta = (n["p50_us"] / o["p50_us"] - 1) * 100 if o["p50_us"] else 0.0
        print(f"{k:14s} {o['p50_us']:11.2f} {n['p50_us']:11.2f} {o['p99_us']:11.2f} {n['p99_us']:11.2f} {delta:8.1f}%")
    print(f"{'olay/s':14s} {off['events_per_s']:11,.0f} {sh['events_per_s']:11,.0f}")
    print(f"shadow niyet: {sh['shadow_intents']} (0 ise reactor hiç çalışmamıştır: ölçüm geçersiz)")
    if not sh["shadow_intents"]:
        print("UYARI: fixture'da açık pozisyonun sembolü yok; karşılaştırma anlamsız.")
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="tests/fixtures/rec-mini")
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--reactors", action="store_true",
                    help="reactor kapalı/shadow karşılaştırması (Gate 4 bütçesi: bookTicker +%%20)")
    a = ap.parse_args(argv)
    if a.reactors:
        return _reactor_report(Path(a.fixture), a.max_files)
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
