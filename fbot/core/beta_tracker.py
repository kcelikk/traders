"""Kayan BTC-beta (Faz 5 K9 girdisi). Saf; bellek sınırlı.

Formül `fbot/research/beta.py` ile aynıdır: beta = Cov(r_alt, r_btc) / Var(r_btc), 1 dk log getiriler.
Yalnızca **ortak zaman damgalı** barlar kullanılır; eksik bar hizalamayı bozmaz.
"""
from __future__ import annotations

import math
from collections import deque

from fbot.research.beta import rolling_beta


class BetaTracker:
    def __init__(self, ref: str = "BTCUSDT", window: int = 240, min_n: int = 30):
        self.ref, self.window, self.min_n = ref, window, min_n
        self._last: dict[str, tuple[int, float]] = {}          # sembol → (start_ms, close)
        self._rets: dict[str, deque] = {}                      # sembol → [(start_ms, log getiri)]

    def on_bar(self, symbol: str, start_ms: int, close: float) -> None:
        prev = self._last.get(symbol)
        self._last[symbol] = (start_ms, close)
        if prev is None or start_ms - prev[0] != 60_000 or prev[1] <= 0 or close <= 0:
            return
        d = self._rets.setdefault(symbol, deque(maxlen=self.window))
        d.append((start_ms, math.log(close / prev[1])))

    def beta(self, symbol: str) -> float | None:
        if symbol == self.ref:
            return 1.0
        rr, sr = self._rets.get(self.ref), self._rets.get(symbol)
        if not rr or not sr:
            return None
        ref_map = dict(rr)
        xs, ys = [], []
        for t, v in sr:
            r = ref_map.get(t)
            if r is not None:
                xs.append(r)
                ys.append(v)
        return rolling_beta(xs, ys, min_n=self.min_n)

    def all_betas(self) -> dict:
        return {s: self.beta(s) for s in self._rets}
