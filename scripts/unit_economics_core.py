"""Unit economics — saf çekirdek. I/O yok."""
from __future__ import annotations

from typing import Sequence

from scripts.latency_core import percentiles

Level = tuple[float, float]  # (fiyat, miktar)


def walk_book(levels: Sequence[Level], notional: float) -> tuple[float | None, float]:
    """Defteri notional (quote) tutarı dolana kadar yürür.
    Döndürür: (ortalama fiyat | None yetersiz derinlikte, dolan miktar)."""
    remaining = notional
    qty_total = 0.0
    cost_total = 0.0
    for price, qty in levels:
        level_notional = price * qty
        take = min(level_notional, remaining)
        q = take / price
        qty_total += q
        cost_total += take
        remaining -= take
        if remaining <= 1e-12:
            return cost_total / qty_total, qty_total
    return None, qty_total


def slippage_bps(levels: Sequence[Level], notional: float, best: float, side: str = "buy") -> float | None:
    """Ortalama dolum fiyatının en iyi fiyata göre sapması, bps. Yetersiz derinlikte None."""
    avg, _ = walk_book(levels, notional)
    if avg is None:
        return None
    diff = (avg - best) if side == "buy" else (best - avg)
    return diff / best * 1e4


def breakeven_move_pct(fee_in_pct: float, fee_out_pct: float, slip_in_pct: float, slip_out_pct: float, funding_pct: float) -> float:
    """Gidiş-dönüş toplam maliyet, notional yüzdesi. Başabaş için gereken minimum lehte hareket."""
    return fee_in_pct + fee_out_pct + slip_in_pct + slip_out_pct + funding_pct


def breakeven_winrate(rr: float, move_pct: float, cost_pct: float) -> float | None:
    """Hedef hareket move_pct (kazançta), zarar move_pct/rr (kayıpta), her işlemde cost_pct maliyet.
    Beklenti = p*(move - cost) - (1-p)*(move/rr + cost) = 0 çözümü. Kazanç maliyeti karşılamıyorsa None."""
    win = move_pct - cost_pct
    loss = move_pct / rr + cost_pct
    if win <= 0:
        return None
    return loss / (win + loss)


def funding_stats(rates: Sequence[float], interval_hours: float) -> dict:
    """Funding oranları (ondalık, aralık başına). Yüzde cinsinden özet."""
    n = len(rates)
    if n == 0:
        return {"n": 0}
    abs_pct = [abs(r) * 100 for r in rates]
    mean_abs = sum(abs_pct) / n
    return {
        "n": n,
        "mean_pct": sum(rates) / n * 100,
        "mean_abs_pct": mean_abs,
        "mean_abs_pct_per_hour": mean_abs / interval_hours,
        "p95_abs_pct": percentiles(abs_pct, (95,))["p95"],
        "max_abs_pct": max(abs_pct),
    }
