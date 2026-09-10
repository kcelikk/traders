from fbot.research.states import StateConfig, directions, label_state

CFG = StateConfig(p_lo=0.2, p_hi=0.8)


def f(**kw):
    base = {"pct_ret_long": 0.5, "pct_rv_long": 0.5, "pct_rv_short": 0.5, "pct_spread": 0.5, "pct_vol_ratio": 0.5,
            "imb_short": 0.1, "ret_short": 0.001}
    base.update(kw)
    return base


def test_state_rules():
    assert label_state(f(), CFG) == "S0"
    assert label_state(f(pct_ret_long=0.9), CFG) == "S1"
    assert label_state(f(pct_ret_long=0.9, pct_rv_long=0.95), CFG) == "S0"   # aşırı genişlemede trend değil
    assert label_state(f(pct_ret_long=0.1), CFG) == "S2"
    assert label_state(f(pct_rv_long=0.1, pct_spread=0.3), CFG) == "S3"
    assert label_state(f(pct_rv_short=0.9, pct_vol_ratio=0.9), CFG) == "S4"


def test_missing_features_yield_S0():
    assert label_state(f(pct_ret_long=None), CFG) == "S0"


def test_directions_per_state():
    assert directions("S1", f()) == [("long", "trend")]
    assert directions("S2", f()) == [("short", "trend")]
    assert directions("S3", f(imb_short=-0.2)) == [("short", "breakout")]
    assert directions("S3", f(imb_short=0.0)) == []
    assert directions("S4", f(ret_short=0.002)) == [("long", "cont"), ("short", "rev")]
    assert directions("S0", f()) == []
