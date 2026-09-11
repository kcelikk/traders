"""Kullanılmayan veriden giriş sinyalleri (H6–H8). Saf; I/O yok, gelecek veriye bakmaz.

Faz 3'te yalnızca fiyat ve hacim türevleri kullanıldı ve hiçbiri maliyeti aşmadı. Buradaki
sinyaller arşivde olup hiç bakılmamış iki kaynağa dayanır: defter derinliği ve konumlanma metrikleri.

Ortak kalıp: ham büyüklük, kendi son `W` barlık geçmişine göre persentile çevrilir; uç bölgede
yön üretilir, ortada sinyal yoktur. Persentil penceresi dolmadan sinyal üretilmez.

  · `book_imb`  (H6) — defter dengesizliği ucu yönü taşır: alış ağırlığı yüksekse long.
  · `oi_change` (H7) — açık pozisyon artışı fiyat yönünü teyit eder: OI artışı ucunda fiyat
                       yönüne uyulur (devam hipotezi).
  · `taker_ls`  (H8) — taker alış/satış oranı ucu tükenmedir: aşırı alış baskısında short.

`oi_change` ve `taker_ls` birbirinin zıddı yönde kurgulanmıştır; ikisi birden doğru olamaz.
Bu kasıtlı: hipotezler birbirini yanlışlayabilsin diye.
"""
from __future__ import annotations

from fbot.research.features import rolling_pct


def _series(bars: list[dict], key: str) -> list[float | None]:
    return [b.get(key) for b in bars]


def _diff(vals: list[float | None]) -> list[float | None]:
    out: list[float | None] = [None]
    for i in range(1, len(vals)):
        a, b = vals[i - 1], vals[i]
        out.append(None if (a is None or b is None or a == 0) else (b - a) / abs(a))
    return out


def _extremes(raw: list[float | None], W: int, p_lo: float, p_hi: float,
              hi_dir: str, lo_dir: str) -> list[str | None]:
    out: list[str | None] = []
    for i in range(len(raw)):
        p = rolling_pct(raw, i, W)
        out.append(None if p is None else hi_dir if p > p_hi else lo_dir if p < p_lo else None)
    return out


def _book_imb(bars, W, p_lo, p_hi):
    return _extremes(_series(bars, "book_imb"), W, p_lo, p_hi, "long", "short")


def _oi_change(bars, W, p_lo, p_hi):
    """OI artışı ucunda fiyatın son bar yönüne uyulur; OI düşüşü ucunda sinyal yok (pozisyon kapanışı)."""
    ch = _extremes(_diff(_series(bars, "open_interest")), W, p_lo, p_hi, "hi", "lo")
    out: list[str | None] = []
    for i, tag in enumerate(ch):
        if tag != "hi" or i == 0:
            out.append(None)
            continue
        up = bars[i]["close"] > bars[i - 1]["close"]
        out.append("long" if up else "short")
    return out


def _taker_ls(bars, W, p_lo, p_hi):
    return _extremes(_series(bars, "taker_ls_ratio"), W, p_lo, p_hi, "short", "long")


SIGNALS = {"book_imb": _book_imb, "oi_change": _oi_change, "taker_ls": _taker_ls}


def signal_series(name: str, bars: list[dict], W: int, p_lo: float, p_hi: float) -> list[str | None]:
    if name not in SIGNALS:
        raise KeyError(f"bilinmeyen sinyal: {name} (geçerli: {', '.join(sorted(SIGNALS))})")
    return SIGNALS[name](bars, W, p_lo, p_hi)
