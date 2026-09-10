"""Maliyet modeli. Saf; Decimal. Oranlar config'den, hard-code yok."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

Level = tuple[Decimal, Decimal]


@dataclass(frozen=True)
class CostConfig:
    maker_rate: Decimal
    taker_rate: Decimal
    bnb_discount: Decimal
    funding_interval_h: int


def commission(notional: Decimal, is_maker: bool, cfg: CostConfig, pay_with_bnb: bool) -> Decimal:
    rate = cfg.maker_rate if is_maker else cfg.taker_rate
    fee = notional * rate
    if pay_with_bnb:
        fee = fee * (Decimal(1) - cfg.bnb_discount)
    return fee


def funding_payment(position_notional: Decimal, rate: Decimal, side: str) -> Decimal:
    """Nakit akışı: pozitif = alınan, negatif = ödenen. Long pozitif oranda öder."""
    sign = Decimal(-1) if side == "long" else Decimal(1)
    return sign * position_notional * rate


def walk_book(levels: Sequence[Level], notional: Decimal) -> tuple[Decimal | None, Decimal]:
    remaining = notional
    qty = Decimal(0)
    cost = Decimal(0)
    for price, lq in levels:
        ln = price * lq
        take = ln if ln < remaining else remaining
        q = take / price
        qty += q
        cost += take
        remaining -= take
        if remaining <= 0:
            return cost / qty, qty
    return None, qty


def slippage_cost(levels: Sequence[Level], notional: Decimal, best: Decimal, side: str) -> Decimal | None:
    """Ortalama dolum ile en iyi fiyat arasındaki farkın miktarla çarpımı (quote cinsinden). Yetersiz derinlikte None."""
    avg, qty = walk_book(levels, notional)
    if avg is None:
        return None
    diff = (avg - best) if side == "buy" else (best - avg)
    return diff * qty
