"""Bir koşu dosyasından yük profili: olay/s, stream kırılımı, loop lag ve kalıcılık kuyruğu.

Kullanım: python -m scripts.trader_load data/recordings/paper/events-*.jsonl.gz [--json]

Gate 1 ölçümü bununla alınır: stream profili ve kalıcılık kuyruğu öncesi/sonrası tek değişkenle
karşılaştırılabilsin diye aynı betik iki kez çalıştırılır. Ölçüm yoksa sayı yazılmaz.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter


def _p(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 2)


def _lines(f):
    """Yazılmakta olan dosya gzip akışını kapatmamış olabilir; okunabilen kısım geçerlidir."""
    while True:
        try:
            line = f.readline()
        except (EOFError, OSError):
            return
        if not line:
            return
        yield line


def scan(paths: list[str]) -> dict:
    kinds: Counter = Counter()
    cats: Counter = Counter()
    lag50: list[float] = []
    lag99: list[float] = []
    lagmax: list[float] = []
    persist: dict | None = None
    first_ns = last_ns = None
    n = 0
    for path in paths:
        with gzip.open(path, "rt") as f:
            for line in _lines(f):
                try:
                    e = json.loads(line)
                except ValueError:
                    break                       # yazılmakta olan dosyanın kuyruğu kesik olabilir
                n += 1
                r = e.get("r")
                if r:
                    first_ns = r if first_ns is None else min(first_ns, r)
                    last_ns = r if last_ns is None else max(last_ns, r)
                cats[e.get("c")] += 1
                s = e.get("s") or "?"
                kinds[s.split("@", 1)[1] if "@" in s else s] += 1
                if e.get("c") == "ctrl" and s == "stats":
                    d = e.get("d") or {}
                    lag = d.get("loop_lag_ms") or {}
                    for key, dst in (("p50", lag50), ("p99", lag99), ("max", lagmax)):
                        if lag.get(key) is not None:
                            dst.append(lag[key])
                elif e.get("c") == "ctrl" and s == "paper_stats":
                    persist = (e.get("d") or {}).get("persist") or persist
    span_s = (last_ns - first_ns) / 1e9 if first_ns and last_ns and last_ns > first_ns else None
    return {"files": len(paths), "events": n, "span_s": round(span_s, 1) if span_s else None,
            "events_per_s": round(n / span_s, 1) if span_s else None,
            "by_category": dict(cats.most_common()), "by_stream_kind": dict(kinds.most_common()),
            "loop_lag_ms": {"samples": len(lag50), "p50_median": _p(lag50, 0.5), "p99_median": _p(lag99, 0.5),
                            "p99_p99": _p(lag99, 0.99), "max": max(lagmax) if lagmax else None},
            "persist": persist}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = scan(a.paths)
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        for k, v in out.items():
            print(f"{k:16s} {v}")


if __name__ == "__main__":
    main(sys.argv[1:])
