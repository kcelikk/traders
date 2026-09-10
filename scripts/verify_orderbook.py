"""Kayıttan local order book replay doğrulaması (Faz 1 kabul kriteri 7).
Kullanım: python -m scripts.verify_orderbook data/recordings/<run_id> [--symbols btcusdt,ethusdt] [--max-files N]

Her sembol için: ctrl/snapshot → apply_snapshot, <s>@depth@100ms → feed; sonuçlar sayılır.
Çapraz kontrol: senkronken gelen her <s>@bookTicker olayında local en iyi bid/ask ile karşılaştırılır.
bookTicker ve depth ayrı yayın hızlarında olduğu için birebir eşleşme beklenmez; eşleşme oranı raporlanır.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

from fbot.events import decode
from fbot.orderbook import LocalOrderBook


def iter_events(run_dir: Path, max_files: int | None):
    files = sorted(run_dir.glob("events-*.jsonl.gz"))
    if max_files:
        files = files[:max_files]
    for path in files:
        try:
            with gzip.open(path, "rb") as f:
                for line in f:
                    if line.endswith(b"\n"):
                        yield decode(line)
        except (EOFError, OSError):
            return  # açık/kesik dosya: okunabilen kadar


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--max-files", type=int, default=None)
    a = ap.parse_args(argv)
    run = Path(a.run_dir)
    want = set(a.symbols.lower().split(",")) if a.symbols else None

    books: dict[str, LocalOrderBook] = {}
    outcomes: dict[str, Counter] = {}
    top_checks: dict[str, Counter] = {}
    first_ok: Counter = Counter()
    n = 0
    for ev in iter_events(run, a.max_files):
        n += 1
        if ev.cat == "ctrl" and ev.stream == "snapshot":
            info = json.loads(ev.raw)
            sym = info["symbol"].lower()
            if want and sym not in want or info.get("status") != 200:
                continue
            ob = books.setdefault(sym, LocalOrderBook())
            out = ob.apply_snapshot(info["body"])
            c = outcomes.setdefault(sym, Counter())
            c["snapshot"] += 1
            for r in out:
                c[r] += 1
            if "applied" in out:
                first_ok[sym] += 1
        elif ev.cat == "public":
            sym = ev.stream.split("@", 1)[0]
            if want and sym not in want:
                continue
            if ev.stream.endswith("@depth@100ms"):
                d = json.loads(ev.raw)["data"]
                ob = books.setdefault(sym, LocalOrderBook())
                r = ob.feed(d)
                outcomes.setdefault(sym, Counter())[r] += 1
            elif ev.stream.endswith("@bookTicker"):
                ob = books.get(sym)
                if ob is not None and ob.synced and ob.last_u is not None:
                    d = json.loads(ev.raw)["data"]
                    tc = top_checks.setdefault(sym, Counter())
                    tc["match" if ob.top_matches(d["b"], d["a"]) else "mismatch"] += 1

    print(f"# Order book replay doğrulaması — `{run.name}`\n")
    print(f"Okunan olay: {n}\n")
    print("| Sembol | snapshot | ilk olay koşulu sağlandı | uygulanan diff | düşülen | tamponlanan | resync (pu kopuşu) | bookTicker eşleşme | eşleşme oranı |")
    print("|---|---|---|---|---|---|---|---|---|")
    for sym in sorted(books):
        c = outcomes.get(sym, Counter())
        tc = top_checks.get(sym, Counter())
        tot = tc["match"] + tc["mismatch"]
        ratio = f"{tc['match'] / tot * 100:.1f}%" if tot else "—"
        print(f"| {sym} | {c['snapshot']} | {first_ok[sym]} | {c['applied']} | {c['dropped']} | {c['buffered']} | {books[sym].resyncs} | {tc['match']}/{tot} | {ratio} |")


if __name__ == "__main__":
    main(sys.argv[1:])
