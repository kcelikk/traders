"""Çekirdek komutları ve deterministik serileştirme. Saf."""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BarClosed:
    symbol: str
    start_ms: int
    end_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trades: int
    buy_volume: Decimal = Decimal(0)  # alıcı agresif hacim (aggTrade m == False)


@dataclass(frozen=True, slots=True)
class StalenessChanged:
    category: str
    stale: bool
    age_ms: int


@dataclass(frozen=True, slots=True)
class PlaceOrder:
    symbol: str
    side: str            # BUY | SELL
    type: str            # MARKET | LIMIT
    qty: Decimal
    price: Decimal | None
    reduce_only: bool
    client_id: str
    time_in_force: str | None


@dataclass(frozen=True, slots=True)
class CancelOrder:
    symbol: str
    client_id: str


@dataclass(frozen=True, slots=True)
class PlaceAlgo:
    symbol: str
    side: str
    type: str            # STOP_MARKET | TAKE_PROFIT_MARKET
    trigger_price: Decimal
    close_position: bool
    working_type: str    # MARK_PRICE | CONTRACT_PRICE
    price_protect: bool
    client_algo_id: str


@dataclass(frozen=True, slots=True)
class CancelAlgo:
    symbol: str
    client_algo_id: str


@dataclass(frozen=True, slots=True)
class StateChanged:
    symbol: str
    from_state: str
    to_state: str
    bar_end_ms: int
    confidence: float | None
    evidence: str
    counter: str


@dataclass(frozen=True, slots=True)
class Alarm:
    kind: str
    detail: str


Command = BarClosed | StalenessChanged | StateChanged | PlaceOrder | CancelOrder | PlaceAlgo | CancelAlgo | Alarm


def canonical(cmd) -> bytes:
    """`Tür|alan1|alan2|...` — alan sırası dataclass tanım sırası; Decimal str() ile (üs gösterimi yok)."""
    parts = [type(cmd).__name__]
    for f in fields(cmd):
        v = getattr(cmd, f.name)
        if isinstance(v, Decimal):
            v = format(v, "f")
        elif isinstance(v, bool):
            v = "1" if v else "0"
        parts.append(str(v))
    return "|".join(parts).encode()
