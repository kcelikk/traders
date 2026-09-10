"""Rate limiter (Faz 9). Saf; saat parametre olarak gelir.

Prompt 4.4 ve doğrulanmış doküman: ağırlık (IP) ve emir (UID) sayaçları **ayrıdır**; emir gönderimi IP ağırlığı
tüketmez ama 10 s ve 1 dk emir sayaçlarını tüketir. Gerçek kullanım cevap header'larından okunur
(`x-mbx-used-weight-*`, `x-mbx-order-count-*`) ya da WS cevabındaki `rateLimits` alanından; tahmini sayaç yetmez.
429 → geri çekilme, 418 → kalıcı ban (kill switch tetikleyicisi).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    weight_1m: int
    orders_10s: int
    orders_1m: int


class _Window:
    def __init__(self, span_ms: int, limit: int):
        self.span_ms, self.limit = span_ms, limit
        self.events: deque = deque()
        self.override: int | None = None      # header'dan gelen gerçek kullanım

    def _trim(self, now_ms: int):
        while self.events and now_ms - self.events[0][0] > self.span_ms:
            self.events.popleft()

    def used(self, now_ms: int) -> int:
        self._trim(now_ms)
        est = sum(n for _, n in self.events)
        return max(est, self.override) if self.override is not None else est

    def add(self, now_ms: int, n: int = 1):
        self._trim(now_ms)
        self.events.append((now_ms, n))
        if self.override is not None:
            self.override += n

    def remaining(self, now_ms: int) -> int:
        return max(0, self.limit - self.used(now_ms))


class RateLimiter:
    def __init__(self, limits: Limits, backoff_ms: int = 10_000, reserve_orders: int = 0):
        self.limits = limits
        self.backoff_ms = backoff_ms
        self.reserve_orders = reserve_orders
        self.w = _Window(60_000, limits.weight_1m)
        self.o10 = _Window(10_000, limits.orders_10s)
        self.o1m = _Window(60_000, limits.orders_1m)
        self.backoff_until_ms = 0
        self.banned = False

    # ---- sorgular
    def allow_weight(self, cost: int, now_ms: int) -> bool:
        return not self.banned and now_ms >= self.backoff_until_ms and self.w.remaining(now_ms) >= cost

    def allow_order(self, now_ms: int, entry: bool = False) -> bool:
        if self.banned or now_ms < self.backoff_until_ms:
            return False
        res = self.reserve_orders if entry else 0
        return self.o10.remaining(now_ms) > res and self.o1m.remaining(now_ms) > res

    def remaining(self, now_ms: int) -> dict:
        return {"weight_1m": self.w.remaining(now_ms), "orders_10s": self.o10.remaining(now_ms),
                "orders_1m": self.o1m.remaining(now_ms)}

    # ---- kayıtlar
    def on_weight(self, cost: int, now_ms: int) -> None:
        self.w.add(now_ms, cost)

    def on_order(self, now_ms: int) -> None:
        self.o10.add(now_ms)
        self.o1m.add(now_ms)

    def sync_headers(self, headers: dict, now_ms: int) -> None:
        h = {k.lower(): v for k, v in headers.items()}
        for key, win in (("x-mbx-used-weight-1m", self.w), ("x-mbx-order-count-10s", self.o10), ("x-mbx-order-count-1m", self.o1m)):
            v = h.get(key)
            if v is not None:
                try:
                    win.override = int(v)
                except ValueError:
                    pass

    def sync_ws(self, rate_limits: list, now_ms: int) -> None:
        for r in rate_limits or []:
            t, iv, n, c = r.get("rateLimitType"), r.get("interval"), r.get("intervalNum"), r.get("count")
            if c is None:
                continue
            if t == "REQUEST_WEIGHT" and iv == "MINUTE":
                self.w.override = c
            elif t == "ORDERS" and iv == "SECOND" and n == 10:
                self.o10.override = c
            elif t == "ORDERS" and iv == "MINUTE":
                self.o1m.override = c

    def on_response(self, status: int, now_ms: int) -> str | None:
        if status == 418:
            self.banned = True
            return "kill_switch"
        if status == 429:
            self.backoff_until_ms = now_ms + self.backoff_ms
            return "backoff"
        return None
