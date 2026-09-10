"""Basit dolum simülatörü. Saf: piyasa görünümü (bookTicker, mark) dışarıdan beslenir, çıktı exec olaylarıdır.

Varsayımlar (docs/design/faz7-paper-trading.md §3): MARKET emirler gecikme sonrası karşı taraf best'te dolar (slippage 0;
80 USDT notional için ölçüldü); algo emirler mark fiyatı tetik seviyesini geçince tetiklenir ve MARKET gibi dolar.
Gecikme sabit `latency_ms` (Faz 0 p50 ≈ 420 ms); dağılım Faz 7'de seed'li örnekleme ile genişletilir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder

MS = 1_000_000


@dataclass(frozen=True)
class SimConfig:
    latency_ms: int
    seed: int


@dataclass
class _Pending:
    cmd: object
    ready_ns: int


class SimExecutor:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.book: dict[str, tuple[Decimal, Decimal]] = {}
        self.pending: list[_Pending] = []
        self.algos: dict[str, PlaceAlgo] = {}
        self.fills_waiting: list[_Pending] = []   # tetiklenen algo → gecikme sonrası dolum

    # ---- piyasa
    def on_book(self, symbol: str, bid: Decimal, ask: Decimal, now_ns: int) -> None:
        self.book[symbol] = (bid, ask)

    def on_mark(self, symbol: str, mark: Decimal, now_ns: int) -> list[dict]:
        out = []
        for cid in sorted(self.algos):
            a = self.algos[cid]
            if a.symbol != symbol:
                continue
            hit = mark <= a.trigger_price if a.type == "STOP_MARKET" and a.side == "SELL" else (
                  mark >= a.trigger_price if a.type == "STOP_MARKET" and a.side == "BUY" else (
                  mark >= a.trigger_price if a.type == "TAKE_PROFIT_MARKET" and a.side == "SELL" else mark <= a.trigger_price))
            if hit:
                del self.algos[cid]
                out.append({"kind": "algo_triggered", "client_algo_id": cid, "t_ns": now_ns})
                reason = "sl" if a.type == "STOP_MARKET" else "tp"
                self.fills_waiting.append(_Pending(("algo_fill", a, reason), now_ns + self.cfg.latency_ms * MS))
        return out

    # ---- emirler
    def submit(self, cmd, now_ns: int) -> None:
        self.pending.append(_Pending(cmd, now_ns + self.cfg.latency_ms * MS))

    def poll(self, now_ns: int) -> list[dict]:
        out = []
        keep = []
        for p in self.pending:
            if p.ready_ns > now_ns:
                keep.append(p)
                continue
            c = p.cmd
            if isinstance(c, PlaceAlgo):
                self.algos[c.client_algo_id] = c
                out.append({"kind": "algo_ack", "client_algo_id": c.client_algo_id, "t_ns": p.ready_ns})
            elif isinstance(c, CancelAlgo):
                self.algos.pop(c.client_algo_id, None)
            elif isinstance(c, PlaceOrder):
                b = self.book.get(c.symbol)
                if b is None:
                    keep.append(p)   # görünüm yok: bekle
                    continue
                price = b[1] if c.side == "BUY" else b[0]
                kind = "exit_fill" if c.reduce_only else "entry_fill_price"
                out.append({"kind": kind, "client_id": c.client_id, "symbol": c.symbol, "price": str(price), "qty": str(c.qty), "t_ns": p.ready_ns})
        self.pending = keep
        keep2 = []
        for p in self.fills_waiting:
            if p.ready_ns > now_ns:
                keep2.append(p); continue
            _, a, reason = p.cmd
            b = self.book.get(a.symbol)
            if b is None:
                keep2.append(p); continue
            price = b[1] if a.side == "BUY" else b[0]
            out.append({"kind": "exit_fill", "client_id": a.client_algo_id, "symbol": a.symbol, "price": str(price), "qty": None, "reason": reason, "t_ns": p.ready_ns})
        self.fills_waiting = keep2
        return out
