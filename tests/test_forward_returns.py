import math

from fbot.research.forward import CostScenario, forward_samples

BAR = 60_000


def mk(i, o, c, spread=2.0, nf=10**15, fr=0.0001):
    return {"symbol": "X", "start_ms": i * BAR, "end_ms": i * BAR + BAR - 1, "open": o, "high": max(o, c), "low": min(o, c),
            "close": c, "volume": 1, "buy_volume": 0.5, "trades": 1, "spread_bps": spread, "funding_rate": fr, "next_funding_ms": nf}


COST = CostScenario(name="tt", fee_in_pct=0.05, fee_out_pct=0.05)


def test_long_sample_math_with_spread_and_fees():
    bars = [mk(0, 100, 100), mk(1, 100, 101), mk(2, 101, 102)]
    states = ["S1", "S0", "S0"]
    dirs = {0: [("long", "trend")]}
    s = forward_samples(bars, states, dirs, horizons=[1], cost=COST, bar_ms=BAR)
    assert len(s) == 1
    x = s[0]
    entry = 100 * (1 + 1.0 / 1e4)   # bar1 open + yarım spread (2 bps / 2)
    exit_ = 101 * (1 - 1.0 / 1e4)   # bar1 close − yarım spread
    assert math.isclose(x["gross_pct"], (exit_ / entry - 1) * 100)
    assert math.isclose(x["cost_pct"], 0.10)   # komisyon; spread fiyatlara işlendi
    assert math.isclose(x["net_pct"], x["gross_pct"] - 0.10)
    assert x["h"] == 1 and x["dir"] == "long" and x["state"] == "S1"


def test_short_sign_and_funding_crossing():
    # ufuk funding zamanını kesiyor: short pozitif oran alır (+), maliyet düşer
    bars = [mk(0, 100, 100, nf=1 * BAR + 10), mk(1, 100, 99, nf=1 * BAR + 10), mk(2, 99, 98, nf=1 * BAR + 10)]
    s = forward_samples(bars, ["S2", "S0", "S0"], {0: [("short", "trend")]}, horizons=[1], cost=COST, bar_ms=BAR)
    x = s[0]
    assert x["gross_pct"] > 0
    assert math.isclose(x["funding_pct"], -0.0001 * 100)  # short alır → maliyet negatif (kazanç)
    assert math.isclose(x["cost_pct"], 0.10 - 0.01)


def test_non_overlapping_and_gap_skip():
    bars = [mk(i, 100, 100) for i in range(8)]
    del bars[5]  # 5. dakika eksik → 4'ten başlayan h=2 örneği atlanır
    states = ["S1"] * 7
    dirs = {i: [("long", "trend")] for i in range(7)}
    s = forward_samples(bars, states, dirs, horizons=[2], cost=COST, bar_ms=BAR)
    idx = [x["i"] for x in s]
    assert idx == [0, 2]  # 0 → (1,2); 2 → (3,4); 4 kırık; 6 için yeterli bar yok
