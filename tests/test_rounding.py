"""Filtre tabanlı yuvarlama (Gate 2.0). Kaynak `Filters`, `pricePrecision` değil."""
from decimal import Decimal as D

import pytest

from fbot.core.rounding import floor_step, fmt_price, fmt_qty, round_tick, trigger_price


def test_quantity_always_rounds_down():
    assert floor_step(D("0.8169"), D("0.001")) == D("0.816")
    assert floor_step(D("3.9"), D("1")) == D("3")


def test_zero_or_negative_step_is_an_error_not_a_silent_pass():
    with pytest.raises(ValueError):
        floor_step(D("1"), D("0"))
    with pytest.raises(ValueError):
        round_tick(D("1"), D("-0.1"), "floor")


@pytest.mark.parametrize("side,role,px,expected", [
    ("long", "SL", "97.51995", "97.51"),     # piyasanın altında → aşağı
    ("long", "TP", "98.9901", "99.00"),      # piyasanın üstünde → yukarı
    ("short", "SL", "102.4801", "102.49"),   # piyasanın üstünde → yukarı
    ("short", "TP", "101.0099", "101.00"),   # piyasanın altında → aşağı
])
def test_trigger_rounds_away_from_the_market(side, role, px, expected):
    """Yanlış yöne yuvarlamak tetiği piyasanın öbür tarafına geçirip -2021 üretebilir."""
    assert trigger_price(D(px), D("0.01"), side, role) == D(expected)


def test_price_already_on_the_tick_is_unchanged():
    for side, role in (("long", "SL"), ("long", "TP"), ("short", "SL"), ("short", "TP")):
        assert trigger_price(D("100.50"), D("0.10"), side, role) == D("100.50")


def test_btcusdt_tick_is_coarser_than_price_precision():
    """Gate 0 bulgusu: tickSize 0,10 · pricePrecision 2. Precision'a yuvarlamak tick'e oturmaz."""
    assert trigger_price(D("74960.75"), D("0.10"), "long", "SL") == D("74960.70")
    assert fmt_price(D("74960.70"), D("0.10")) == "74960.7"


def test_formatting_follows_the_filter_not_a_fixed_precision():
    assert fmt_qty(D("0.8169"), D("0.001")) == "0.816"
    assert fmt_qty(D("7.9"), D("1")) == "7"
    assert fmt_price(D("100.50"), D("0.01")) == "100.50"


def test_formatting_refuses_a_price_that_is_not_on_the_tick():
    """Sessizce yuvarlamak, yuvarlamanın tek yerde olması kuralını deler."""
    with pytest.raises(ValueError, match="tick"):
        fmt_price(D("100.505"), D("0.01"))


def test_unknown_side_or_role_is_rejected():
    with pytest.raises(ValueError):
        trigger_price(D("1"), D("0.1"), "uzun", "SL")
    with pytest.raises(ValueError):
        trigger_price(D("1"), D("0.1"), "long", "STOP")
