"""Maliyet sürüklenmesi izleyicisi (prompt BÖLÜM 6.4). Saf.

Kayan pencerede üç oran ölçülür ve eşik aşımında **alarm** üretilir; işlem engellenmez:
  · komisyon / brüt kâr
  · toplam maliyet (komisyon + funding + slippage) / sermaye
  · işlem başına ortalama net sonuç

Alarm her işlemde değil, eşik ihlali başladığında bir kez üretilir (gürültü yapmaz); eşiğin altına
dönülüp yeniden aşılırsa tekrar üretilir.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from fbot.core.commands import Alarm

METRICS = ("commission_to_gross", "cost_to_capital", "net_per_trade")


@dataclass(frozen=True)
class CostDriftConfig:
    window_ms: int
    capital_usdt: Decimal
    commission_to_gross_max: Decimal | None = None
    cost_to_capital_max: Decimal | None = None
    net_per_trade_min: Decimal | None = None
    min_trades: int = 10


class CostDriftMonitor:
    def __init__(self, cfg: CostDriftConfig):
        self.cfg = cfg
        self.trades: deque = deque()
        self.breached: set = set()

    def _trim(self, now_ms: int) -> None:
        while self.trades and now_ms - self.trades[0][0] > self.cfg.window_ms:
            self.trades.popleft()

    def on_trade(self, t: dict, now_ms: int) -> list[Alarm]:
        self.trades.append((now_ms, t))
        self._trim(now_ms)
        r = self._compute(now_ms)
        out = []
        for name in METRICS:
            if name in r["alarms"] and name not in self.breached:
                self.breached.add(name)
                out.append(Alarm(kind=f"cost_drift:{name}", detail=r["detail"][name]))
            elif name not in r["alarms"]:
                self.breached.discard(name)
        return out

    def report(self, now_ms: int) -> dict:
        self._trim(now_ms)
        return self._compute(now_ms)

    def _compute(self, now_ms: int) -> dict:
        n = len(self.trades)
        gross_profit = Decimal(0)
        commission = funding = slippage = Decimal(0)
        net_sum = Decimal(0)
        for _, t in self.trades:
            net = Decimal(str(t["net_pct"]))
            notional = Decimal(str(t.get("notional", 0)))
            c = Decimal(str(t.get("commission_usdt", 0)))
            f = Decimal(str(t.get("funding_usdt", 0)))
            s = Decimal(str(t.get("slippage_usdt", 0)))
            commission += c
            funding += f
            slippage += s
            net_sum += net
            gross_usdt = net * notional / 100 + c + f + s
            if gross_usdt > 0:
                gross_profit += gross_usdt
        cfg = self.cfg
        c2g = (commission / gross_profit) if gross_profit > 0 else None
        total = commission + funding + slippage
        c2c = (total / cfg.capital_usdt) if cfg.capital_usdt > 0 else None
        npt = (net_sum / n) if n else None
        alarms, detail = [], {}
        enough = n >= cfg.min_trades
        if enough and cfg.commission_to_gross_max is not None and c2g is not None and c2g > cfg.commission_to_gross_max:
            alarms.append("commission_to_gross")
            detail["commission_to_gross"] = f"komisyon/brüt kâr {c2g:.2f} > eşik {cfg.commission_to_gross_max} ({n} işlem)"
        if enough and cfg.cost_to_capital_max is not None and c2c is not None and c2c > cfg.cost_to_capital_max:
            alarms.append("cost_to_capital")
            detail["cost_to_capital"] = f"toplam maliyet/sermaye {c2c:.4f} > eşik {cfg.cost_to_capital_max} ({total:.2f} USDT, {n} işlem)"
        if enough and cfg.net_per_trade_min is not None and npt is not None and npt < cfg.net_per_trade_min:
            alarms.append("net_per_trade")
            detail["net_per_trade"] = f"işlem başına net {npt:.3f}% < eşik {cfg.net_per_trade_min}% ({n} işlem)"
        return {"trades": n, "commission_usdt": commission, "funding_usdt": funding, "slippage_usdt": slippage,
                "gross_profit_usdt": gross_profit, "commission_to_gross": c2g, "cost_to_capital": c2c,
                "net_per_trade_pct": npt, "alarms": alarms, "detail": detail}
