"""Dolum simülatörü — L2 defter yürüyüşlü (ADR 0013).

Kurallar, olgun açık kaynak simülatörlerin **doğrulanmış** davranışından alınmıştır (kod kopyalanmadı):
  · NautilusTrader (LGPL-3.0, backtest matching engine): MARKET emirler "walk crossed book levels as a taker";
    kısmi dolum "available crossed size is smaller than its remaining quantity"; `STOP_MARKET` tetik sonrası
    defteri yürür; tek-tick kayma "does not apply to L2 or L3 books"; `random_seed` ile tekrarlanabilirlik.
  · Hummingbot (Apache-2.0, paper_trade connector): market emirler defteri yürür, **ağırlıklı ortalama fiyat**;
    limit emir karşı taraf fiyatı limiti geçince dolar; açık yürütme gecikmesi.

Bilinen sınır: **kuyruk pozisyonu modellenmez** → maker dolum oranı iyimserdir. Her paper raporunda belirtilir.
Saf değildir yalnızca sırası bakımından: piyasa görünümü dışarıdan beslenir, saat parametre olarak gelir.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal

from fbot.core.commands import CancelAlgo, CancelOrder, PlaceAlgo, PlaceOrder

MS = 1_000_000
Level = tuple[Decimal, Decimal]


@dataclass(frozen=True)
class SimConfig:
    latency_ms: int                      # temel gecikme (Faz 0: p50 ≈ 420 ms)
    seed: int                            # tüm rastlantı seed'li (Rule Zero #5)
    jitter_ms: int = 0                   # gecikme dağılımı: [latency, latency + jitter]
    partial_timeout_ms: int | None = None  # kısmi dolumda kalan miktar bu süre sonunda iptal
    prob_fill_on_touch: float = 0.0      # limit emir fiyata dokunup geçmezse dolma olasılığı (Nautilus prob_fill_on_limit)


@dataclass
class _Pending:
    cmd: object
    ready_ns: int
    remaining: Decimal | None = None
    first_ns: int | None = None


@dataclass
class _Book:
    bids: list = field(default_factory=list)   # azalan
    asks: list = field(default_factory=list)   # artan

    def side(self, is_buy: bool) -> list:
        return self.asks if is_buy else self.bids


def walk(levels: list[Level], qty: Decimal) -> tuple[Decimal | None, Decimal]:
    """`qty` kadar miktarı defterden alır. Döndürür: (ağırlıklı ortalama fiyat, dolan miktar)."""
    filled = Decimal(0)
    cost = Decimal(0)
    for price, avail in levels:
        take = avail if avail < (qty - filled) else (qty - filled)
        filled += take
        cost += take * price
        if filled >= qty:
            break
    if filled <= 0:
        return None, Decimal(0)
    return cost / filled, filled


class SimExecutor:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.books: dict[str, _Book] = {}
        self.top: dict[str, tuple[Decimal, Decimal]] = {}   # bookTicker (yalnızca maker geçiş kontrolü)
        self.pending_orders: list[_Pending] = []
        self.pending_ctrl: list[_Pending] = []
        self.algos: dict[str, PlaceAlgo] = {}
        self.triggered: list[_Pending] = []
        self.positions: dict[str, tuple[str, Decimal]] = {}   # pos_id → (sembol, miktar)
        self.rng = random.Random(cfg.seed)

    # ---------------- piyasa görünümü
    def on_depth(self, symbol: str, bids: list[Level], asks: list[Level], now_ns: int) -> None:
        b = self.books.setdefault(symbol, _Book())
        b.bids = sorted(bids, key=lambda x: -x[0])
        b.asks = sorted(asks, key=lambda x: x[0])

    def on_book(self, symbol: str, bid: Decimal, ask: Decimal, now_ns: int) -> None:
        """bookTicker: yalnızca en iyi fiyat. Defter yoksa tek seviyelik defter olarak kullanılmaz (ADR 0013 §7)."""
        self.top[symbol] = (bid, ask)

    def on_mark(self, symbol: str, mark: Decimal, now_ns: int) -> list[dict]:
        out = []
        for cid in sorted(self.algos):
            a = self.algos[cid]
            if a.symbol != symbol:
                continue
            if self._hit(a, mark):
                del self.algos[cid]
                out.append({"kind": "algo_triggered", "client_algo_id": cid, "t_ns": now_ns})
                self.triggered.append(_Pending(a, now_ns + self._latency()))
        return out

    @staticmethod
    def _hit(a: PlaceAlgo, mark: Decimal) -> bool:
        down = a.type == "STOP_MARKET" if a.side == "SELL" else a.type == "TAKE_PROFIT_MARKET"
        return mark <= a.trigger_price if down else mark >= a.trigger_price

    def set_position(self, pos_id: str, symbol: str, qty: Decimal) -> None:
        """closePosition emirleri için miktar kaynağı."""
        self.positions[pos_id] = (symbol, qty)

    # ---------------- emirler
    def submit(self, cmd, now_ns: int) -> None:
        p = _Pending(cmd, now_ns + self._latency())
        if isinstance(cmd, PlaceOrder):
            p.remaining = cmd.qty
            p.first_ns = None
            self.pending_orders.append(p)
        else:
            self.pending_ctrl.append(p)

    def _latency(self) -> int:
        j = self.rng.randint(0, self.cfg.jitter_ms) if self.cfg.jitter_ms else 0
        return (self.cfg.latency_ms + j) * MS

    def poll(self, now_ns: int) -> list[dict]:
        out: list[dict] = []
        out += self._process_ctrl(now_ns)
        out += self._process_triggered(now_ns)
        out += self._process_orders(now_ns)
        return out

    # ---------------- iç
    def _process_ctrl(self, now_ns: int) -> list[dict]:
        out, keep = [], []
        for p in self.pending_ctrl:
            if p.ready_ns > now_ns:
                keep.append(p)
                continue
            c = p.cmd
            if isinstance(c, PlaceAlgo):
                self.algos[c.client_algo_id] = c
                out.append({"kind": "algo_ack", "client_algo_id": c.client_algo_id, "t_ns": p.ready_ns})
            elif isinstance(c, CancelAlgo):
                self.algos.pop(c.client_algo_id, None)
            elif isinstance(c, CancelOrder):
                self.pending_orders = [x for x in self.pending_orders if getattr(x.cmd, "client_id", None) != c.client_id]
        self.pending_ctrl = keep
        return out

    def _process_triggered(self, now_ns: int) -> list[dict]:
        """Tetiklenen algo emir: taker gibi defteri yürür (Nautilus: 'walk crossed levels after triggering')."""
        out, keep = [], []
        for p in self.triggered:
            a: PlaceAlgo = p.cmd
            if p.ready_ns > now_ns:
                keep.append(p)
                continue
            pos_id = a.client_algo_id.split("-")[0]
            sym, qty = self.positions.get(pos_id, (a.symbol, None))
            if qty is None or qty <= 0:
                continue   # pozisyon yok: closePosition emri işlem üretmez
            book = self.books.get(a.symbol)
            if book is None:
                keep.append(p)
                continue
            price, filled = walk(book.side(a.side == "BUY"), qty)
            if price is None:
                keep.append(p)
                continue
            out.append({"kind": "exit_fill", "client_id": a.client_algo_id, "symbol": a.symbol, "price": str(price),
                        "qty": str(filled), "reason": "sl" if a.type == "STOP_MARKET" else "tp",
                        "partial": filled < qty, "t_ns": now_ns, "ready_ns": p.ready_ns})
        self.triggered = keep
        return out

    def _process_orders(self, now_ns: int) -> list[dict]:
        out, keep = [], []
        for p in self.pending_orders:
            c: PlaceOrder = p.cmd
            if p.ready_ns > now_ns:
                keep.append(p)
                continue
            if p.first_ns is None:
                p.first_ns = now_ns
            is_buy = c.side == "BUY"
            price, filled = (None, Decimal(0))
            if c.type == "LIMIT":
                price, filled = self._limit_fill(c, p, is_buy)
            else:
                book = self.books.get(c.symbol)
                if book is not None:
                    price, filled = walk(book.side(is_buy), p.remaining)
            if price is not None and filled > 0:
                p.remaining -= filled
                out.append({"kind": "exit_fill" if c.reduce_only else "entry_fill_price", "client_id": c.client_id,
                            "symbol": c.symbol, "price": str(price), "qty": str(filled),
                            "partial": p.remaining > 0, "t_ns": now_ns, "ready_ns": p.ready_ns,
                            **({"reason": "app_exit"} if c.reduce_only else {})})
            if p.remaining > 0:
                to = self.cfg.partial_timeout_ms
                if to is not None and now_ns - p.first_ns >= to * MS:
                    out.append({"kind": "order_expired", "client_id": c.client_id, "symbol": c.symbol,
                                "remaining": str(p.remaining), "t_ns": now_ns})
                else:
                    keep.append(p)
        self.pending_orders = keep
        return out

    def _limit_fill(self, c: PlaceOrder, p: _Pending, is_buy: bool):
        """Maker: piyasa limiti **geçerse** dolar (dokunma yetmez); dolum fiyatı limittir."""
        top = self.top.get(c.symbol)
        book = self.books.get(c.symbol)
        best = None
        if top is not None:
            best = top[1] if is_buy else top[0]
        elif book is not None:
            side = book.side(is_buy)
            best = side[0][0] if side else None
        if best is None:
            return None, Decimal(0)
        crossed = best < c.price if is_buy else best > c.price
        touched = best == c.price
        if not crossed and not (touched and self.rng.random() < self.cfg.prob_fill_on_touch):
            return None, Decimal(0)
        return c.price, p.remaining
