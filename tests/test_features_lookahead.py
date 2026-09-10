"""Look-ahead yasağı: bar t'nin feature'ları yalnızca ≤ t verisinden. Kesme testi bit-eşit olmalı."""
import math

from fbot.research.features import FeatureConfig, compute_features, rolling_pct

CFG = FeatureConfig(W=10, N_short=2, N_long=3)


def bars(n, start=0):
    out = []
    p = 100.0
    for i in range(n):
        p *= 1 + ((i % 7) - 3) / 1000
        out.append({"symbol": "X", "start_ms": start + i * 60_000, "end_ms": start + i * 60_000 + 59_999,
                    "open": p * 0.999, "high": p * 1.001, "low": p * 0.998, "close": p, "volume": 10 + (i % 5),
                    "buy_volume": 5 + (i % 3), "trades": 3, "spread_bps": 1.0, "funding_rate": 0.0001, "next_funding_ms": 10**12})
    return out


def test_truncation_does_not_change_past_features():
    full = compute_features(bars(40), CFG)
    cut = compute_features(bars(25), CFG)
    assert cut == full[:25]


def test_rolling_pct_looks_back_only_and_excludes_current():
    vals = [1, 2, 3, 4, 5, 100, 6]
    # i=5: önceki W=5 değer [1..5], hepsi ≤ 100 → 1.0 ; i=6: önceki 5 [2,3,4,5,100], ≤6 olanlar 4 → 0.8
    assert rolling_pct(vals, 5, 5) == 1.0
    assert rolling_pct(vals, 6, 5) == 0.8
    assert rolling_pct(vals, 2, 5) is None  # yetersiz geçmiş


def test_feature_values_are_defined_from_history():
    f = compute_features(bars(40), CFG)
    assert f[0]["ret_long"] is None and f[3]["ret_long"] is not None
    b = bars(40)
    assert math.isclose(f[3]["ret_long"], math.log(b[3]["close"] / b[0]["close"]))
    assert f[3]["rv_long"] > 0
    assert -1.0 <= f[3]["imb_short"] <= 1.0
    assert f[CFG.W + CFG.N_long]["pct_ret_long"] is not None and f[CFG.W]["pct_ret_long"] is None
