"""Konsolun BTC-beta net maruziyeti: gerçek miktar × beta, yön işaretli (F07/K9)."""
from fbot.api.server import beta_net_usdt


def test_long_and_short_offset_each_other():
    betas = {"ALTUSDT": 1.5, "XUSDT": 1.0}
    pos = [{"symbol": "ALTUSDT", "side": "long", "notional_usdt": 100.0},
           {"symbol": "XUSDT", "side": "short", "notional_usdt": 50.0}]
    assert beta_net_usdt(pos, betas) == 100.0        # +150 − 50


def test_symbol_without_beta_is_skipped_not_assumed_one():
    assert beta_net_usdt([{"symbol": "YUSDT", "side": "long", "notional_usdt": 80.0}], {}) is None
    out = beta_net_usdt([{"symbol": "YUSDT", "side": "long", "notional_usdt": 80.0},
                         {"symbol": "XUSDT", "side": "long", "notional_usdt": 80.0}], {"XUSDT": 1.0})
    assert out == 80.0


def test_no_open_position_is_zero():
    assert beta_net_usdt([], {"XUSDT": 1.0}) == 0.0
