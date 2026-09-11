"""Arşiv `metrics` dosyaları: açık pozisyon ve konumlanma oranları. Saf; I/O yok.

15 dakikada bir yayınlanır. İçerik fiyattan bağımsız bilgi taşır:
  · `sum_open_interest` — açık pozisyon miktarı
  · `count_long_short_ratio` — hesap sayısına göre long/short oranı
  · `sum_toptrader_long_short_ratio` — büyük hesapların pozisyon oranı
  · `sum_taker_long_short_vol_ratio` — taker alış/satış hacim oranı

**Look-ahead koruması:** bir dakikaya yalnızca o dakikaya kadar yayınlanmış son değer taşınır.
İleri taşıma yapılır, geri taşıma asla. İlk örnekten önceki dakikalar boştur.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

M = 60_000
FIELDS = {"open_interest": "sum_open_interest", "open_interest_usdt": "sum_open_interest_value",
          "toptrader_ls_ratio": "sum_toptrader_long_short_ratio", "account_ls_ratio": "count_long_short_ratio",
          "taker_ls_ratio": "sum_taker_long_short_vol_ratio"}


def parse_metrics(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(StringIO(text)):
        try:
            t = datetime.strptime(r["create_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            out.append({"t_ms": int(t.timestamp() * 1000), "symbol": r["symbol"],
                        **{k: float(r[v]) for k, v in FIELDS.items()}})
        except (TypeError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda r: r["t_ms"])


def metrics_per_minute(rows: list[dict], until_ms: int) -> dict[int, dict]:
    """Dakika → son bilinen metrik. İlk örnekten önceki dakikalar yok; değer ileri taşınır."""
    out: dict[int, dict] = {}
    if not rows:
        return out
    i, cur = 0, None
    start = rows[0]["t_ms"] // M * M
    for t in range(start, until_ms + M, M):
        while i < len(rows) and rows[i]["t_ms"] <= t:
            cur = rows[i]
            i += 1
        if cur is not None:
            out[t] = {k: cur[k] for k in FIELDS}
    return out
