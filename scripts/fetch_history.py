"""data.binance.vision günlük dosyalarını indirir ve SHA-256 checksum ile doğrular (stdlib).
Kullanım: python -m scripts.fetch_history --symbols BTCUSDT,ETHUSDT --start 2026-08-09 --end 2026-09-08 [--out data/history]
Veri tipleri: aggTrades, markPriceKlines/1m, premiumIndexKlines/1m. Var olan ve doğrulanmış dosya atlanır; 404 raporlanır."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/daily"


def url_for(kind: str, sym: str, d: str) -> str:
    if kind == "aggTrades":
        return f"{BASE}/aggTrades/{sym}/{sym}-aggTrades-{d}.zip"
    return f"{BASE}/{kind}/{sym}/1m/{sym}-1m-{d}.zip"


def fetch(url: str, timeout=120) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="data/history")
    ap.add_argument("--kinds", default="aggTrades,markPriceKlines,premiumIndexKlines")
    a = ap.parse_args(argv)
    d0, d1 = date.fromisoformat(a.start), date.fromisoformat(a.end)
    days = [(d0 + timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)]
    stats = {"downloaded": 0, "skipped": 0, "missing": [], "checksum_fail": [], "bytes": 0}
    for sym in a.symbols.split(","):
        for kind in a.kinds.split(","):
            outdir = Path(a.out) / kind / sym
            outdir.mkdir(parents=True, exist_ok=True)
            for d in days:
                url = url_for(kind, sym, d)
                dst = outdir / url.rsplit("/", 1)[1]
                ok = dst.with_suffix(".zip.ok")
                if dst.exists() and ok.exists():
                    stats["skipped"] += 1
                    continue
                body = fetch(url)
                if body is None:
                    stats["missing"].append(f"{kind}/{sym}/{d}")
                    continue
                chk = fetch(url + ".CHECKSUM")
                expected = chk.decode().split()[0] if chk else None
                actual = hashlib.sha256(body).hexdigest()
                if expected is None or expected != actual:
                    stats["checksum_fail"].append(f"{kind}/{sym}/{d}")
                    continue
                dst.write_bytes(body)
                ok.write_text(actual + "\n")
                stats["downloaded"] += 1
                stats["bytes"] += len(body)
                print(f"{kind}/{sym}/{d} {len(body)/1e6:.1f} MB", flush=True)
    print(json.dumps(stats))


if __name__ == "__main__":
    main(sys.argv[1:])
