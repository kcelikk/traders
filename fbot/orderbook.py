"""Local order book — Binance USDⓈ-M dokümanındaki kural seti. Saf; I/O yok.

Kurallar (doğrulandı, docs/binance-api-verification.md §11):
  snapshot öncesi olaylar tamponlanır · u < lastUpdateId olan olay düşülür ·
  ilk işlenen olayda U <= lastUpdateId <= u · sonraki her olayda pu == önceki u, değilse baştan (snapshot) ·
  miktar mutlak, 0 → seviye silinir · olmayan seviyeyi silmek normaldir.
"""
from __future__ import annotations

from decimal import Decimal


class LocalOrderBook:
    def __init__(self):
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.last_update_id: int | None = None
        self.last_u: int | None = None
        self.synced = False
        self.buffer: list[dict] = []
        self.resyncs = 0
        self.applied = 0
        self.dropped = 0

    # ---- giriş noktaları
    def apply_snapshot(self, snapshot: dict) -> list[str]:
        self.bids = {Decimal(p): Decimal(q) for p, q in snapshot["bids"]}
        self.asks = {Decimal(p): Decimal(q) for p, q in snapshot["asks"]}
        self.last_update_id = snapshot["lastUpdateId"]
        self.last_u = None
        self.synced = True
        pending, self.buffer = self.buffer, []
        out = []
        for d in pending:
            r = self._process(d)
            out.append(r)
            if r == "resync":
                break
        return out

    def feed(self, d: dict) -> str:
        if not self.synced:
            self.buffer.append(d)
            return "buffered"
        return self._process(d)

    # ---- çekirdek
    def _process(self, d: dict) -> str:
        U, u, pu = d["U"], d["u"], d.get("pu")
        if self.last_u is None:
            if u < self.last_update_id:
                self.dropped += 1
                return "dropped"
            if not (U <= self.last_update_id <= u):
                return self._resync()
        elif pu != self.last_u:
            return self._resync()
        self._apply(d)
        self.last_u = u
        self.applied += 1
        return "applied"

    def _resync(self) -> str:
        self.synced = False
        self.last_u = None
        self.resyncs += 1
        return "resync"

    def _apply(self, d: dict):
        for book, key in ((self.bids, "b"), (self.asks, "a")):
            for p, q in d.get(key, ()):
                price, qty = Decimal(p), Decimal(q)
                if qty == 0:
                    book.pop(price, None)
                else:
                    book[price] = qty

    # ---- sorgular
    def best_bid(self) -> tuple[Decimal, Decimal] | None:
        if not self.bids:
            return None
        p = max(self.bids)
        return p, self.bids[p]

    def best_ask(self) -> tuple[Decimal, Decimal] | None:
        if not self.asks:
            return None
        p = min(self.asks)
        return p, self.asks[p]

    def top_matches(self, bid_price: str, ask_price: str) -> bool:
        bb, ba = self.best_bid(), self.best_ask()
        return bb is not None and ba is not None and bb[0] == Decimal(bid_price) and ba[0] == Decimal(ask_price)
