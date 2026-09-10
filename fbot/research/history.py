"""Binance geçmiş aggTrades (data.binance.vision) → çekirdekle aynı barlar. Saf; dosya okuma scripts/ tarafında."""
from __future__ import annotations

import bisect

from fbot.core.commands import BarClosed
from fbot.core.market import SymbolMarket

AGG_HEADER = "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker"


def agg_row_to_trade(row: str) -> dict:
    """CSV satırı → stream aggTrade sözlüğü (p/q string, T int, m bool)."""
    a, p, q, _f, _l, t, m = row.rstrip("\n").split(",")
    return {"e": "aggTrade", "a": int(a), "p": p, "q": q, "T": int(t), "m": m == "true"}


def bars_from_agg_rows(symbol: str, rows, bar_ms: int, market: SymbolMarket | None = None) -> list[BarClosed]:
    """Aynı SymbolMarket ile bar üretimi; `market` verilirse gün sınırları arasında state taşınır."""
    m = market or SymbolMarket(symbol, bar_ms)
    out: list[BarClosed] = []
    for row in rows:
        if row.startswith("agg_trade_id"):
            continue
        out += m.on_agg_trade(agg_row_to_trade(row))
    return out


def attach_mark(bars: list[dict], marks: dict[int, float]) -> None:
    """marks: open_time_ms → mark kapanış fiyatı (markPriceKlines 1m)."""
    for b in bars:
        b["mark"] = marks.get(b["start_ms"])


def attach_funding(bars: list[dict], funding: list[tuple[int, float]]) -> None:
    """funding: (fundingTime_ms, rate) artan sırada. Bar için bitişten sonraki ilk funding anı ve o anın oranı."""
    times = [t for t, _ in funding]
    for b in bars:
        i = bisect.bisect_right(times, b["end_ms"])
        if i < len(funding):
            b["next_funding_ms"], b["funding_rate"] = funding[i]
        else:
            b["next_funding_ms"], b["funding_rate"] = None, None
