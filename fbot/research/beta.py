"""BTC-beta: alt coin getirisinin BTC getirisine duyarlılığı (Faz 5 K9 girdisi). Saf.

beta = Cov(r_alt, r_btc) / Var(r_btc), 1 dk log getiriler üzerinde kayan pencere.
5 farklı altcoin pozisyonu pratikte tek bir BTC pozisyonudur; net maruziyet bu katsayıyla ölçülür.
"""
from __future__ import annotations

import math


def rolling_beta(btc_rets: list[float], alt_rets: list[float], min_n: int = 10) -> float | None:
    n = min(len(btc_rets), len(alt_rets))
    if n < min_n:
        return None
    x, y = btc_rets[-n:], alt_rets[-n:]
    mx, my = sum(x) / n, sum(y) / n
    var = sum((a - mx) ** 2 for a in x)
    if var <= 0:
        return None
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return cov / var


def _log_rets(bars: list[dict]) -> dict[int, float]:
    out = {}
    prev = None
    for b in bars:
        c = b["close"]
        if prev is not None and prev[1] > 0 and c > 0 and b["start_ms"] - prev[0] == 60_000:
            out[b["start_ms"]] = math.log(c / prev[1])
        prev = (b["start_ms"], c)
    return out


def beta_series(btc_bars: list[dict], alt_bars: list[dict], window: int = 240, min_n: int = 30) -> list[dict]:
    """Ortak zaman damgalarında kayan beta. Eksik bar atlanır (hizalama şart)."""
    rb, ra = _log_rets(btc_bars), _log_rets(alt_bars)
    ts = sorted(set(rb) & set(ra))
    out = []
    bx, ay = [], []
    for t in ts:
        bx.append(rb[t]); ay.append(ra[t])
        if len(bx) > window:
            del bx[:-window]; del ay[:-window]
        b = rolling_beta(bx, ay, min_n=min_n)
        if b is not None:
            out.append({"t_ms": t, "beta": b, "n": len(bx)})
    return out
