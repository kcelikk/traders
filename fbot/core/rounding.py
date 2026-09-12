"""Borsa filtrelerine göre yuvarlama — tek doğruluk kaynağı. Saf, `Decimal`.

Kaynak `Filters` (`step_size`, `tick_size`), **`pricePrecision` değil**. Gate 0 doğrulaması
(`docs/binance-api-gate0-dogrulama.md` §4) BTCUSDT testnet'te `tickSize=0.10` ile
`pricePrecision=2`'nin uyuşmadığını gösterdi: precision'a yuvarlamak tick'e oturmayan fiyat üretir.

Tetik fiyatı **piyasadan uzağa** yuvarlanır. Sebep validite: long'un stop'u piyasanın altında,
take profit'i üstünde olmak zorundadır; yanlış yöne yuvarlamak tetiği piyasanın öbür tarafına
geçirip emri anında tetiklenebilir (-2021) hâle getirebilir. Tick boyutları küçük olduğu için
PnL etkisi ihmal edilebilir, validite etkisi gerçektir.
"""
from __future__ import annotations

from decimal import Decimal

ROLES = ("SL", "TP")


def floor_step(qty: Decimal, step: Decimal) -> Decimal:
    """Miktar her zaman aşağı: yukarı yuvarlamak bakiyeyi ve notional'ı aşabilir."""
    if step <= 0:
        raise ValueError(f"step_size pozitif olmalı: {step}")
    return (qty // step) * step


def round_tick(px: Decimal, tick: Decimal, direction: str) -> Decimal:
    if tick <= 0:
        raise ValueError(f"tick_size pozitif olmalı: {tick}")
    if direction not in ("floor", "ceil"):
        raise ValueError(f"yön 'floor' veya 'ceil' olmalı: {direction!r}")
    q = px / tick
    n = q.to_integral_value(rounding="ROUND_FLOOR" if direction == "floor" else "ROUND_CEILING")
    return n * tick


def trigger_price(px: Decimal, tick: Decimal, side: str, role: str) -> Decimal:
    """Koruma tetiği: piyasadan uzağa yuvarla.

    long SL (piyasanın altında) → aşağı · long TP (üstünde) → yukarı
    short SL (üstünde) → yukarı · short TP (altında) → aşağı
    """
    if side not in ("long", "short"):
        raise ValueError(f"yön 'long' veya 'short' olmalı: {side!r}")
    if role not in ROLES:
        raise ValueError(f"rol {ROLES} içinde olmalı: {role!r}")
    below = (side == "long") == (role == "SL")      # tetik piyasanın altında mı?
    return round_tick(px, tick, "floor" if below else "ceil")


def _decimals(unit: Decimal) -> int:
    """Filtre biriminden ondalık basamak sayısı: 0.001 → 3, 1 → 0, 10 → 0."""
    e = unit.normalize().as_tuple().exponent
    return max(0, -int(e))


def fmt_qty(qty: Decimal, step: Decimal) -> str:
    return f"{floor_step(qty, step):.{_decimals(step)}f}"


def fmt_price(px: Decimal, tick: Decimal) -> str:
    """Zaten tick'e oturmuş bir fiyatı biçimlendirir; oturmuyorsa hata verir (sessizce yuvarlamaz)."""
    if px % tick != 0:
        raise ValueError(f"fiyat tick'e oturmuyor: {px} % {tick}")
    return f"{px:.{_decimals(tick)}f}"
