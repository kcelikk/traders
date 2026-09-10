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


@dataclass(frozen=True, slots=True)
class StalenessChanged:
    category: str
    stale: bool
    age_ms: int


Command = BarClosed | StalenessChanged


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
