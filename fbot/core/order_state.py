"""Emir durum makinesi (Faz 9). Saf.

Tek doğruluk kaynağı user data akışıdır (Binance: volatil piyasada REST gecikebilir).
`tradeId` ile tekrar bastırma, kısmi dolum birikimi, sıra dışı olayda geriye düşmeme.
Durumlar Binance alanlarından: `X` (order status), `x` (execution type) — docs/binance-api-verification.md §12.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class OrderStatus(Enum):
    NEW = "NEW"
    UNKNOWN = "UNKNOWN"                       # yürütme durumu bilinmiyor (timeout / 503 / -2022)
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    EXPIRED_IN_MATCH = "EXPIRED_IN_MATCH"     # Self-Trade Prevention
    REJECTED = "REJECTED"


TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.EXPIRED_IN_MATCH, OrderStatus.REJECTED}
# UNKNOWN, NEW'in üstünde ama terminalin altındadır: bilinmezlik bir ilerlemedir, sonuç değildir.
_RANK = {OrderStatus.NEW: 0, OrderStatus.UNKNOWN: 1, OrderStatus.PARTIALLY_FILLED: 1, OrderStatus.FILLED: 2,
         OrderStatus.CANCELED: 2, OrderStatus.EXPIRED: 2, OrderStatus.EXPIRED_IN_MATCH: 2, OrderStatus.REJECTED: 2}


@dataclass
class Order:
    client_id: str
    symbol: str
    status: OrderStatus
    filled: Decimal = Decimal(0)
    cost: Decimal = Decimal(0)
    commission: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    order_id: int | None = None
    trades: set = field(default_factory=set)
    dup_trades: int = 0
    external: bool = False
    reduce_only: bool = False
    last_t_ms: int | None = None

    @property
    def avg_price(self) -> Decimal | None:
        return (self.cost / self.filled) if self.filled > 0 else None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL


class OrderBook:
    """İsim çakışmasın diye `fbot.orderbook.LocalOrderBook` ile karıştırma: bu emir defteridir, fiyat defteri değil."""

    def __init__(self):
        self.orders: dict[str, Order] = {}
        self._stats = {"fills": 0, "dup_trades": 0, "expired_in_match": 0, "rejected": 0, "external": 0, "canceled": 0}

    def apply(self, ev: dict) -> Order:
        cid = ev["client_id"]
        o = self.orders.get(cid)
        if o is None:
            o = self.orders[cid] = Order(client_id=cid, symbol=ev.get("symbol", ""), status=OrderStatus.NEW,
                                         external=bool(ev.get("liquidation")) or cid.startswith(("autoclose-", "adl_autoclose")),
                                         reduce_only=bool(ev.get("reduce_only")))
            if o.external:
                self._stats["external"] += 1
        if ev.get("order_id") is not None:
            o.order_id = ev["order_id"]
        new = OrderStatus(ev["status"]) if ev.get("status") in OrderStatus.__members__ else o.status
        if ev.get("kind") == "order_fill":
            tid = ev.get("trade_id")
            if tid is not None and tid in o.trades:
                o.dup_trades += 1
                self._stats["dup_trades"] += 1
                return o
            if tid is not None:
                o.trades.add(tid)
            qty = Decimal(str(ev.get("qty") or "0"))
            px = Decimal(str(ev.get("price") or "0"))
            cum = ev.get("cum_qty")
            if cum is not None and Decimal(str(cum)) < o.filled:
                return o          # sıra dışı eski olay: geriye düşme
            o.filled += qty
            o.cost += qty * px
            o.commission += Decimal(str(ev.get("commission") or "0"))
            o.realized_pnl += Decimal(str(ev.get("realized_pnl") or "0"))
            self._stats["fills"] += 1
        if _RANK.get(new, 0) >= _RANK.get(o.status, 0):
            o.status = new
            if new == OrderStatus.EXPIRED_IN_MATCH:
                self._stats["expired_in_match"] += 1
            elif new == OrderStatus.REJECTED:
                self._stats["rejected"] += 1
            elif new == OrderStatus.CANCELED:
                self._stats["canceled"] += 1
        o.last_t_ms = ev.get("t_ms", o.last_t_ms)
        return o

    def open_orders(self) -> list[Order]:
        return [o for o in self.orders.values() if not o.is_terminal]

    def stats(self) -> dict:
        return {**self._stats, "tracked": len(self.orders), "open": len(self.open_orders())}
