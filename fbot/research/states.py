"""Durum etiketleme: en fazla 5 durum, her biri en fazla 2 koşulun AND'i (docs/research/hipotezler.md)."""
from __future__ import annotations

from dataclasses import dataclass

STATES = ("S0", "S1", "S2", "S3", "S4")


@dataclass(frozen=True)
class StateConfig:
    p_lo: float
    p_hi: float


def _in_band(x, lo, hi):
    return x is not None and lo <= x <= hi


def label_state(f: dict, cfg: StateConfig) -> str:
    pr, prv_l, prv_s = f.get("pct_ret_long"), f.get("pct_rv_long"), f.get("pct_rv_short")
    psp, pvr = f.get("pct_spread"), f.get("pct_vol_ratio")
    # Öncelik sırası sabit ve deterministik: S4 (aşırı) > S1/S2 (trend) > S3 (sıkışma)
    if prv_s is not None and pvr is not None and prv_s > cfg.p_hi and pvr > cfg.p_hi:
        return "S4"
    if pr is not None and pr > cfg.p_hi and _in_band(prv_l, cfg.p_lo, cfg.p_hi):
        return "S1"
    if pr is not None and pr < cfg.p_lo and _in_band(prv_l, cfg.p_lo, cfg.p_hi):
        return "S2"
    if prv_l is not None and prv_l < cfg.p_lo and (psp is None or psp < cfg.p_hi):
        return "S3"  # spread persentili yoksa (sabit spread) yalnızca volatilite koşulu
    return "S0"


def directions(state: str, f: dict) -> list[tuple[str, str]]:
    """(yön, hipotez etiketi) listesi."""
    if state == "S1":
        return [("long", "trend")]
    if state == "S2":
        return [("short", "trend")]
    if state == "S3":
        imb = f.get("imb_short") or 0.0
        if imb > 0:
            return [("long", "breakout")]
        if imb < 0:
            return [("short", "breakout")]
        return []
    if state == "S4":
        r = f.get("ret_short") or 0.0
        cont = "long" if r >= 0 else "short"
        rev = "short" if cont == "long" else "long"
        return [(cont, "cont"), (rev, "rev")]
    return []
