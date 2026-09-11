"""Kullanılmayan veriden giriş sinyalleri (H6–H8). Saf; I/O yok, gelecek veriye bakmaz.

Faz 3'te yalnızca fiyat ve hacim türevleri kullanıldı ve hiçbiri maliyeti aşmadı. Buradaki
sinyaller arşivde olup hiç bakılmamış iki kaynağa dayanır: defter derinliği ve konumlanma metrikleri.

Ortak kalıp: ham büyüklük, kendi son `W` barlık geçmişine göre persentile çevrilir; uç bölgede
yön üretilir, ortada sinyal yoktur. Persentil penceresi dolmadan sinyal üretilmez.

  · `book_imb`  (H6) — defter dengesizliği ucu yönü taşır: alış ağırlığı yüksekse long.
  · `oi_change` (H7) — açık pozisyon artışı fiyat yönünü teyit eder: OI artışı ucunda fiyat
                       yönüne uyulur (devam hipotezi).
  · `taker_ls`  (H8) — taker alış/satış oranı ucu tükenmedir: aşırı alış baskısında short.
  · `liq_exhaust` (H9)  — likidasyon kaskadı tükenmedir: yoğun long likidasyonu (zorunlu satış)
                          dip işaretidir → long; yoğun short likidasyonu tepe işaretidir → short.
  · `liq_follow`  (H10) — kaskad fiyatı ittirir: likidasyon baskısının yönüne uyulur. H9'un zıddı.

Likidasyon verisi Binance arşivinde yoktur; yalnızca kendi kaydımızdaki `forceOrder` akışından gelir.

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


def _liq_net(bars):
    """Net likidasyon baskısı: long likidasyonu satış baskısı (negatif), short likidasyonu alış (pozitif).
    Ölçek büyüklükten bağımsız olsun diye toplam likidasyon hacmine bölünür."""
    out: list[float | None] = []
    for b in bars:
        lo, sh = b.get("liq_long_usdt"), b.get("liq_short_usdt")
        if lo is None or sh is None:
            out.append(None)
            continue
        tot = lo + sh
        out.append(None if tot <= 0 else (sh - lo) / tot)
    return out


def _liq_strength(bars):
    """Kaskadın büyüklüğü: toplam likidasyon notional'ı. Yön taşımaz, şiddet taşır."""
    return [None if (b.get("liq_long_usdt") is None or b.get("liq_short_usdt") is None)
            else (b["liq_long_usdt"] + b["liq_short_usdt"]) for b in bars]


def _liq_signal(bars, W, p_lo, p_hi, follow: bool):
    """Yalnızca **şiddetli** kaskadlarda sinyal: toplam likidasyon persentili üst bantta olmalı.
    Yön net baskının işaretinden gelir; `follow` yönü, tersi tükenme hipotezidir."""
    strong = _extremes(_liq_strength(bars), W, p_lo, p_hi, "hi", "lo")
    net = _liq_net(bars)
    out: list[str | None] = []
    for i, tag in enumerate(strong):
        n = net[i]
        if tag != "hi" or n is None or n == 0:
            out.append(None)
            continue
        pressure = "long" if n > 0 else "short"      # short likidasyonu = alış baskısı
        out.append(pressure if follow else ("short" if pressure == "long" else "long"))
    return out


def _liq_exhaust(bars, W, p_lo, p_hi):
    return _liq_signal(bars, W, p_lo, p_hi, follow=False)


def _liq_follow(bars, W, p_lo, p_hi):
    return _liq_signal(bars, W, p_lo, p_hi, follow=True)


SIGNALS = {"book_imb": _book_imb, "oi_change": _oi_change, "taker_ls": _taker_ls,
           "liq_exhaust": _liq_exhaust, "liq_follow": _liq_follow}


def signal_series(name: str, bars: list[dict], W: int, p_lo: float, p_hi: float) -> list[str | None]:
    if name not in SIGNALS:
        raise KeyError(f"bilinmeyen sinyal: {name} (geçerli: {', '.join(sorted(SIGNALS))})")
    return SIGNALS[name](bars, W, p_lo, p_hi)
