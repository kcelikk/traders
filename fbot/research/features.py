"""Rolling feature'lar. Yalnızca geçmişe bakar; bar i için yalnızca bars[:i+1] kullanılır (ADR 0008 §2)."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureConfig:
    W: int          # persentil ve hacim ortalaması penceresi (bar)
    N_short: int    # kısa pencere (bar)
    N_long: int     # uzun pencere (bar)


def rolling_pct(values: list, i: int, W: int) -> float | None:
    """values[i]'nin önceki W değer içindeki persentili (≤ oranı). Mevcut değer dahil edilmez.
    Pencere sabitse (tüm değerler eşit) persentil anlamsızdır → None (sabit spread artefaktı, ADR 0009 §3)."""
    if i < W:
        return None
    window = values[i - W:i]
    if any(v is None for v in window) or values[i] is None:
        return None
    if min(window) == max(window) == values[i]:
        return None
    return sum(1 for v in window if v <= values[i]) / W


def _log_ret(bars, i, n):
    if i < n or bars[i - n]["close"] <= 0:
        return None
    return math.log(bars[i]["close"] / bars[i - n]["close"])


def _rv(bars, i, n):
    if i < n:
        return None
    acc = 0.0
    for k in range(i - n + 1, i + 1):
        r = math.log(bars[k]["close"] / bars[k - 1]["close"])
        acc += r * r
    return math.sqrt(acc)


def _imb(bars, i, n):
    if i < n - 1:
        return None
    v = sum(b["volume"] for b in bars[i - n + 1:i + 1])
    if v <= 0:
        return None
    bv = sum(b["buy_volume"] for b in bars[i - n + 1:i + 1])
    return (2 * bv - v) / v


def _vol_ratio(bars, i, W):
    if i < W:
        return None
    avg = sum(b["volume"] for b in bars[i - W:i]) / W
    return bars[i]["volume"] / avg if avg > 0 else None


def compute_features(bars: list[dict], cfg: FeatureConfig) -> list[dict]:
    """Her bar için ham feature'lar + rolling persentiller. Yetersiz geçmişte None."""
    n = len(bars)
    ret_s = [_log_ret(bars, i, cfg.N_short) for i in range(n)]
    ret_l = [_log_ret(bars, i, cfg.N_long) for i in range(n)]
    rv_s = [_rv(bars, i, cfg.N_short) for i in range(n)]
    rv_l = [_rv(bars, i, cfg.N_long) for i in range(n)]
    imb_s = [_imb(bars, i, cfg.N_short) for i in range(n)]
    vr = [_vol_ratio(bars, i, cfg.W) for i in range(n)]
    spread = [b.get("spread_bps") for b in bars]
    out = []
    for i in range(n):
        out.append({
            "ret_short": ret_s[i], "ret_long": ret_l[i], "rv_short": rv_s[i], "rv_long": rv_l[i],
            "imb_short": imb_s[i], "vol_ratio": vr[i], "spread_bps": spread[i],
            "pct_ret_long": rolling_pct(ret_l, i, cfg.W), "pct_rv_long": rolling_pct(rv_l, i, cfg.W),
            "pct_rv_short": rolling_pct(rv_s, i, cfg.W), "pct_vol_ratio": rolling_pct(vr, i, cfg.W),
            "pct_spread": rolling_pct(spread, i, cfg.W),
        })
    return out
