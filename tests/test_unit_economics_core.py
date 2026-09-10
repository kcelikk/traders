"""Unit economics çekirdeği testleri. Saf fonksiyonlar."""
import pytest

from scripts.unit_economics_core import (
    walk_book,
    slippage_bps,
    breakeven_move_pct,
    breakeven_winrate,
    funding_stats,
)


# defter: [(fiyat, miktar)] — ask tarafı artan, bid tarafı azalan
ASKS = [(100.0, 1.0), (100.1, 2.0), (100.2, 10.0)]
BIDS = [(99.9, 1.0), (99.8, 2.0), (99.7, 10.0)]


def test_walk_book_fills_within_first_level():
    avg, filled = walk_book(ASKS, notional=50.0)
    assert filled == pytest.approx(0.5)
    assert avg == pytest.approx(100.0)


def test_walk_book_crosses_levels_weighted_average():
    # 100 USDT @100 (1.0 adet) + 100.1 USDT @100.1 (1.0 adet) = 200.1 notional
    avg, filled = walk_book(ASKS, notional=200.1)
    assert filled == pytest.approx(2.0)
    assert avg == pytest.approx(200.1 / 2.0)


def test_walk_book_insufficient_depth_returns_none():
    avg, filled = walk_book(ASKS, notional=10_000.0)
    assert avg is None
    assert filled == pytest.approx(13.0)


def test_slippage_bps_buy_vs_best_ask():
    # 200.1 notional → ort 100.05, best 100.0 → 5 bps
    assert slippage_bps(ASKS, notional=200.1, best=100.0) == pytest.approx(5.0)


def test_slippage_bps_sell_uses_negative_direction():
    # bid tarafında ort < best → pozitif slippage döner
    avg, _ = walk_book(BIDS, notional=99.9 + 99.8)
    assert avg == pytest.approx((99.9 + 99.8) / 2)
    assert slippage_bps(BIDS, notional=99.9 + 99.8, best=99.9, side="sell") == pytest.approx(
        (99.9 - (99.9 + 99.8) / 2) / 99.9 * 1e4
    )


def test_breakeven_move_is_sum_of_round_trip_costs():
    # taker giriş + taker çıkış: 0.05 + 0.05; slippage 2 yön × 1 bps; funding 0.01
    m = breakeven_move_pct(fee_in_pct=0.05, fee_out_pct=0.05, slip_in_pct=0.01, slip_out_pct=0.01, funding_pct=0.01)
    assert m == pytest.approx(0.13)


def test_breakeven_winrate_formula():
    # R:R = 1: kazanç = move - cost, kayıp = move + cost → p*(W) = (1-p)*L
    # move 1.0, cost 0.1 → W=0.9, L=1.1 → p = 1.1/2.0 = 0.55
    assert breakeven_winrate(rr=1.0, move_pct=1.0, cost_pct=0.1) == pytest.approx(0.55)


def test_breakeven_winrate_without_cost_is_classic():
    assert breakeven_winrate(rr=2.0, move_pct=1.0, cost_pct=0.0) == pytest.approx(1 / 3)


def test_breakeven_winrate_impossible_when_cost_exceeds_move():
    assert breakeven_winrate(rr=1.0, move_pct=0.1, cost_pct=0.2) is None


def test_funding_stats_per_interval_and_hourly():
    rates = [0.0001, -0.0001, 0.0003]  # 8 saatlik oranlar
    s = funding_stats(rates, interval_hours=8)
    assert s["n"] == 3
    assert s["mean_abs_pct"] == pytest.approx((0.0001 + 0.0001 + 0.0003) / 3 * 100)
    assert s["mean_pct"] == pytest.approx(0.0001 * 100)
    assert s["mean_abs_pct_per_hour"] == pytest.approx(s["mean_abs_pct"] / 8)
    assert s["p95_abs_pct"] == pytest.approx(0.0003 * 100)
