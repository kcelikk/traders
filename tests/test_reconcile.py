from decimal import Decimal

from fbot.core.reconcile import ExchangeSnapshot, reconcile


def internal(**kw):
    base = {"positions": {"p1": {"symbol": "BTCUSDT", "side": "long", "qty": Decimal("0.001"), "algos": {"p1-SL-v1", "p1-TP-v1"}}}}
    base.update(kw)
    return base


def snapshot(**kw):
    base = dict(positions={"BTCUSDT": {"side": "long", "qty": Decimal("0.001")}},
                open_algos={"BTCUSDT": {"p1-SL-v1", "p1-TP-v1"}}, open_orders={}, leverage={"BTCUSDT": 10}, position_mode="ONE_WAY")
    base.update(kw)
    return ExchangeSnapshot(**base)


def test_match_is_ok():
    r = reconcile(internal(), snapshot(), expected_leverage={"BTCUSDT": 10})
    assert r.ok and r.mismatches == [] and r.unprotected == []


def test_exchange_position_unknown_to_us_is_mismatch_and_unprotected():
    r = reconcile({"positions": {}}, snapshot(open_algos={}), expected_leverage={"BTCUSDT": 10})
    assert not r.ok
    assert any(m.startswith("position_unknown:BTCUSDT") for m in r.mismatches)
    assert r.unprotected == ["BTCUSDT"]


def test_missing_protection_is_flagged_even_if_positions_match():
    r = reconcile(internal(), snapshot(open_algos={"BTCUSDT": {"p1-SL-v1"}}), expected_leverage={"BTCUSDT": 10})
    assert not r.ok and "algo_missing:BTCUSDT:p1-TP-v1" in r.mismatches and r.unprotected == []


def test_qty_side_leverage_mode_mismatches():
    r = reconcile(internal(), snapshot(positions={"BTCUSDT": {"side": "short", "qty": Decimal("0.002")}}, leverage={"BTCUSDT": 5}, position_mode="HEDGE"),
                  expected_leverage={"BTCUSDT": 10})
    assert {"side_mismatch:BTCUSDT", "qty_mismatch:BTCUSDT", "leverage_mismatch:BTCUSDT", "position_mode:HEDGE"} <= set(r.mismatches)


def test_internal_position_missing_on_exchange():
    r = reconcile(internal(), snapshot(positions={}, open_algos={}), expected_leverage={"BTCUSDT": 10})
    assert "position_missing_on_exchange:BTCUSDT" in r.mismatches and "algo_orphan:BTCUSDT:p1-SL-v1" not in r.mismatches


def test_orphan_algos_on_exchange_are_reported():
    r = reconcile({"positions": {}}, snapshot(positions={}, open_algos={"ETHUSDT": {"zzz"}}), expected_leverage={})
    assert r.mismatches == ["algo_orphan:ETHUSDT:zzz"] and not r.ok
