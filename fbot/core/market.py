"""Sembol piyasa görünümü ve bar üretici. Saf; Decimal."""
from __future__ import annotations

from decimal import Decimal

from fbot.core.commands import BarClosed


class SymbolMarket:
    __slots__ = ("symbol", "bar_ms", "best_bid", "best_ask", "best_bid_qty", "best_ask_qty", "book_update_id",
                 "last_price", "last_qty", "last_trade_ms", "last_agg_id", "mark_price", "index_price",
                 "funding_rate", "next_funding_ms", "_bar")

    def __init__(self, symbol: str, bar_ms: int):
        self.symbol = symbol
        self.bar_ms = bar_ms
        self.best_bid = self.best_ask = self.best_bid_qty = self.best_ask_qty = None
        self.book_update_id = None
        self.last_price = self.last_qty = None
        self.last_trade_ms = None
        self.last_agg_id = None
        self.mark_price = self.index_price = self.funding_rate = None
        self.next_funding_ms = None
        self._bar = None  # [start_ms, o, h, l, c, vol, n]

    def on_book_ticker(self, d: dict) -> list:
        self.best_bid, self.best_bid_qty = Decimal(d["b"]), Decimal(d["B"])
        self.best_ask, self.best_ask_qty = Decimal(d["a"]), Decimal(d["A"])
        self.book_update_id = d.get("u")
        return []

    def on_mark_price(self, d: dict) -> list:
        self.mark_price = Decimal(d["p"])
        self.index_price = Decimal(d["i"]) if "i" in d else None
        self.funding_rate = Decimal(d["r"]) if "r" in d else None
        self.next_funding_ms = d.get("T")
        return []

    def on_agg_trade(self, d: dict) -> list:
        p, q, T = Decimal(d["p"]), Decimal(d["q"]), d["T"]
        bq = q if not d.get("m", False) else Decimal(0)
        self.last_price, self.last_qty, self.last_trade_ms, self.last_agg_id = p, q, T, d.get("a")
        start = (T // self.bar_ms) * self.bar_ms
        out = []
        b = self._bar
        if b is None or start != b[0]:
            if b is not None:
                out.append(self._close(b))
            self._bar = [start, p, p, p, p, q, 1, bq]
        else:
            if p > b[2]:
                b[2] = p
            if p < b[3]:
                b[3] = p
            b[4] = p
            b[5] += q
            b[6] += 1
            b[7] += bq
        return out

    def _close(self, b) -> BarClosed:
        return BarClosed(self.symbol, b[0], b[0] + self.bar_ms - 1, b[1], b[2], b[3], b[4], b[5], b[6], b[7])
