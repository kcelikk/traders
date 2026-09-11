"""Arşiv `bookDepth` dosyaları: defter derinliği ve dengesizliği. Saf; I/O yok, saat okumaz.

Binance her ~dakika, mid fiyattan ±%1'den ±%5'e kadar 20 seviyede defterdeki miktarı ve notional'ı
yayınlar. Buradan çıkardığımız iki büyüklük:

  · **imb** — (alış notional − satış notional) / toplam. −1 ile +1 arası, yönsüz ölçek.
  · **depth_usdt** — banttaki toplam notional. Likidite büyüklüğü.

Negatif `percentage` alış tarafı (mid'in altı), pozitif satış tarafıdır.
Bir dakikada birden çok örnek varsa **sonuncusu** alınır: bar kapanışına en yakın gözlem odur.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

M = 60_000


def _ts(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def parse_book_depth(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(StringIO(text)):
        try:
            out.append({"t_ms": _ts(r["timestamp"]), "pct": float(r["percentage"]),
                        "depth": float(r["depth"]), "notional": float(r["notional"])})
        except (TypeError, ValueError, KeyError):
            continue                      # bozuk satır atlanır; dosyanın kalanı kullanılır
    return out


def imbalance_per_minute(rows: list[dict], band_pct: float = 1.0) -> dict[int, dict]:
    """Dakika → {imb, depth_usdt}. Yalnızca örnek bulunan dakikalar döner; eksik dakika sıfır değildir."""
    by_sample: dict[int, dict] = {}
    for r in rows:
        if abs(r["pct"]) > band_pct + 1e-9:
            continue
        s = by_sample.setdefault(r["t_ms"], {"bid": 0.0, "ask": 0.0})
        s["bid" if r["pct"] < 0 else "ask"] += r["notional"]
    out: dict[int, dict] = {}
    for t in sorted(by_sample):
        s = by_sample[t]
        total = s["bid"] + s["ask"]
        if total <= 0:
            continue
        out[t // M * M] = {"imb": (s["bid"] - s["ask"]) / total, "depth_usdt": total}   # aynı dakikada son örnek kazanır
    return out
