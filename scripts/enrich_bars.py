"""bars.jsonl'e arşivden gelen iki yeni veri kaynağını ekler: defter dengesizliği ve konumlanma metrikleri.

Bu iki kaynak fiyat ve hacimden **bağımsız** bilgi taşır; Faz 3'te hiç kullanılmamıştı.
Eklenen alanlar (yoksa `null`, sıfır değil):
  · `book_imb`      — ±band içinde (alış − satış) / toplam notional
  · `depth_usdt`    — banttaki toplam notional
  · `open_interest`, `open_interest_usdt`
  · `account_ls_ratio`, `toptrader_ls_ratio`, `taker_ls_ratio`
  · `liq_long_usdt`, `liq_short_usdt`, `liq_count` — yalnızca `--liquidations` verilirse

Look-ahead koruması: her değer yalnızca kendi dakikasına veya sonrasına taşınır, geriye asla.

Likidasyonda eksik dakika **sıfırdır**, null değil: olay yoksa gerçekten likidasyon olmamıştır.
Defter ve metrik verisinde durum farklıdır, orada örnek yokluğu "bilinmiyor" demektir. Ama
likidasyon dosyası hiç verilmemişse alanlar null kalır; "sıfır likidasyon" iddiası edilmez.

Kullanım: python -m scripts.enrich_bars <bars.jsonl> <out.jsonl> [--history data/history] [--band 1.0]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fbot.research.bookdepth import imbalance_per_minute, parse_book_depth
from fbot.research.metrics import metrics_per_minute, parse_metrics

M = 60_000
DEPTH_FIELDS = ("book_imb", "depth_usdt")
METRIC_FIELDS = ("open_interest", "open_interest_usdt", "toptrader_ls_ratio", "account_ls_ratio", "taker_ls_ratio")
LIQ_FIELDS = ("liq_long_usdt", "liq_short_usdt", "liq_count")


def _read_zip(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        with zipfile.ZipFile(path) as z:
            with z.open(z.namelist()[0]) as f:
                return io.TextIOWrapper(f, encoding="utf-8").read()
    except (zipfile.BadZipFile, OSError):
        return None


def _days(ms_values) -> list[str]:
    return sorted({datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d") for t in ms_values})


def _load_liquidations(path: Path | None) -> dict | None:
    if path is None:
        return None
    per: dict[tuple[str, int], dict] = {}
    try:
        for line in Path(path).open():
            if line.strip():
                r = json.loads(line)
                per[(r["symbol"], r["start_ms"])] = {k: r.get(k) for k in LIQ_FIELDS}
    except (OSError, ValueError, KeyError):
        return None
    return per


def enrich(src: Path, out: Path, history: Path, band_pct: float = 1.0, liquidations: Path | None = None) -> dict:
    by_sym: dict[str, list[int]] = defaultdict(list)
    rows = []
    for line in Path(src).open():
        if line.strip():
            b = json.loads(line)
            rows.append(b)
            by_sym[b["symbol"]].append(b["start_ms"])

    depth: dict[str, dict] = {}
    metrics: dict[str, dict] = {}
    for sym, times in by_sym.items():
        d_all, m_rows = {}, []
        for day in _days(times):
            t = _read_zip(Path(history) / "bookDepth" / sym / f"{sym}-bookDepth-{day}.zip")
            if t:
                d_all.update(imbalance_per_minute(parse_book_depth(t), band_pct))
            t = _read_zip(Path(history) / "metrics" / sym / f"{sym}-metrics-{day}.zip")
            if t:
                m_rows += parse_metrics(t)
        depth[sym] = d_all
        metrics[sym] = metrics_per_minute(sorted(m_rows, key=lambda r: r["t_ms"]), max(times)) if m_rows else {}

    liq = _load_liquidations(liquidations)
    n_depth = n_metrics = n_liq = 0
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with Path(out).open("w") as fo:
        for b in rows:
            minute = b["start_ms"] // M * M
            d = depth.get(b["symbol"], {}).get(minute)
            m = metrics.get(b["symbol"], {}).get(minute)
            n_depth += d is not None
            n_metrics += m is not None
            b["book_imb"] = d["imb"] if d else None
            b["depth_usdt"] = d["depth_usdt"] if d else None
            for k in METRIC_FIELDS:
                b[k] = m[k] if m else None
            if liq is None:
                for k in LIQ_FIELDS:
                    b[k] = None
            else:
                v = liq.get((b["symbol"], minute))
                n_liq += v is not None
                for k in LIQ_FIELDS:
                    b[k] = (v or {}).get(k, 0) if v else 0      # olay yoksa gerçekten sıfır
            fo.write(json.dumps(b, separators=(",", ":")) + "\n")
    return {"bars": len(rows), "with_depth": n_depth, "with_metrics": n_metrics,
            "with_liquidations": n_liq, "symbols": len(by_sym), "band_pct": band_pct, "out": str(out)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--history", default="data/history")
    ap.add_argument("--band", type=float, default=1.0)
    ap.add_argument("--liquidations", default=None, help="scripts.extract_liquidations çıktısı")
    a = ap.parse_args(argv)
    print(json.dumps(enrich(Path(a.src), Path(a.out), Path(a.history), a.band,
                            Path(a.liquidations) if a.liquidations else None), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
