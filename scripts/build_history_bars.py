"""Geçmiş aggTrades zip'lerinden bars.jsonl (araştırma girdisi). Bar üretimi çekirdek SymbolMarket ile.
Kullanım: python -m scripts.build_history_bars --symbols ... --start ... --end ... --out data/research/hist-30d/bars.jsonl
Spread: data/research/spread_medians.json (Faz 1 kaydından ölçülen medyan, sembol başına, SABİT). Funding: REST fundingRate geçmişi."""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fbot.core.market import SymbolMarket
from fbot.gateway.rest import get
from fbot.research.history import attach_funding, attach_mark, bars_from_agg_rows


def days_between(s, e):
    d0, d1 = date.fromisoformat(s), date.fromisoformat(e)
    return [(d0 + timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)]


def read_zip_lines(path: Path):
    with zipfile.ZipFile(path) as z:
        with z.open(z.namelist()[0]) as f:
            for line in io.TextIOWrapper(f, encoding="utf-8"):
                yield line


def mark_closes(path: Path) -> dict[int, float]:
    out = {}
    for line in read_zip_lines(path):
        if line.startswith("open_time"):
            continue
        p = line.split(",")
        out[int(p[0])] = float(p[4])
    return out


def funding_history(sym: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    out = []
    t = start_ms
    while t < end_ms:
        st, _, body = get("/fapi/v1/fundingRate", {"symbol": sym, "startTime": t, "endTime": end_ms, "limit": 1000})
        if st != 200:
            raise RuntimeError(f"fundingRate HTTP {st}")
        rows = json.loads(body)
        if not rows:
            break
        out += [(r["fundingTime"], float(r["fundingRate"])) for r in rows]
        t = rows[-1]["fundingTime"] + 1
        if len(rows) < 1000:
            break
        time.sleep(0.2)
    return sorted(set(out))


def spread_medians(rec_bars: Path) -> dict[str, float]:
    vals = {}
    if not rec_bars.exists():
        return {}
    for line in rec_bars.read_text().splitlines():
        if line.strip():
            b = json.loads(line)
            if b.get("spread_bps") is not None:
                vals.setdefault(b["symbol"], []).append(b["spread_bps"])
    return {s: statistics.median(v) for s, v in vals.items()}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--history", default="data/history")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rec-bars", default="data/research/rec-72h/bars.jsonl")
    ap.add_argument("--bar-ms", type=int, default=60_000)
    a = ap.parse_args(argv)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    days = days_between(a.start, a.end)
    spreads = spread_medians(Path(a.rec_bars))
    (out.parent / "spread_medians.json").write_text(json.dumps({"source": a.rec_bars, "median_spread_bps": spreads, "note": "SABİT spread; Faz 1 kaydı medyanı"}, indent=1))
    start_ms = int(datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int((datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc) + timedelta(days=2)).timestamp() * 1000)
    total = 0
    stats = {}
    with out.open("w") as fo:
        for sym in a.symbols.split(","):
            fund = funding_history(sym, start_ms - 9 * 3600 * 1000, end_ms)
            market = SymbolMarket(sym, a.bar_ms)
            n_days = 0
            sym_bars = 0
            for d in days:
                agg = Path(a.history) / "aggTrades" / sym / f"{sym}-aggTrades-{d}.zip"
                if not agg.exists():
                    continue
                n_days += 1
                bars = bars_from_agg_rows(sym, read_zip_lines(agg), a.bar_ms, market)
                rows = [{"symbol": sym, "start_ms": b.start_ms, "end_ms": b.end_ms, "open": float(b.open), "high": float(b.high),
                         "low": float(b.low), "close": float(b.close), "volume": float(b.volume), "buy_volume": float(b.buy_volume),
                         "trades": b.trades, "spread_bps": spreads.get(sym), "index": None} for b in bars]
                mp = Path(a.history) / "markPriceKlines" / sym / f"{sym}-1m-{d}.zip"
                attach_mark(rows, mark_closes(mp) if mp.exists() else {})
                attach_funding(rows, fund)
                for r in rows:
                    fo.write(json.dumps(r, separators=(",", ":")) + "\n")
                sym_bars += len(rows)
            total += sym_bars
            stats[sym] = {"days": n_days, "bars": sym_bars, "spread_bps": spreads.get(sym), "funding_points": len(fund)}
            print(json.dumps({sym: stats[sym]}), flush=True)
    print(json.dumps({"bars": total, "out": str(out)}))


if __name__ == "__main__":
    main(sys.argv[1:])
