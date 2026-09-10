"""Risk Engine (Faz 5): saf assess, K1–K18, çıkışlar engellenmez."""
from decimal import Decimal

from fbot.core.position import Filters
from fbot.core.risk import EntryIntent, RiskConfig, RiskInputs, RunawayDetector, assess

F = Filters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), min_notional=Decimal("50"), tick_size=Decimal("0.1"))
CFG = RiskConfig(max_positions=5, gross_cap_usdt=Decimal("400"), beta_cap_usdt=Decimal("300"), leverage={"BTCUSDT": 10, "ETHUSDT": 10},
                 default_leverage=5, margin_buffer=Decimal("0.2"), spread_max_bps=Decimal("5"), participation_max=Decimal("0.2"),
                 slippage_max_bps=Decimal("3"), cooldown_ms=60_000, cooldown_loss_ms=300_000, cooldown_stp_ms=120_000,
                 reserve_orders=3, backoff_ms=10_000, skew_max_ms=1000, warmup_bars=480)


def inputs(**kw):
    base = dict(kill_switch=False, reconciled=True, warmup_bars={"BTCUSDT": 500}, stale={"public": False, "market": False}, skew_ms=10,
                open_positions={}, pending_entries=set(), gross_usdt=Decimal("0"), beta_exposure_usdt=Decimal("0"), betas={"BTCUSDT": Decimal("1")},
                account_leverage={"BTCUSDT": 10}, available_balance=Decimal("100"), filters={"BTCUSDT": F}, spread_bps={"BTCUSDT": Decimal("0.5")},
                depth_notional={"BTCUSDT": Decimal("5000")}, slippage_bps={"BTCUSDT": Decimal("0.1")}, last_exit_ms={}, last_exit_was_loss={},
                last_stp_ms={}, orders_left_10s=100, orders_left_1m=500, last_429_ms=None, banned=False, now_ms=1_000_000)
    base.update(kw)
    return RiskInputs(**base)


def intent(**kw):
    base = dict(symbol="BTCUSDT", side="long", notional=Decimal("80"), price=Decimal("78000"), reduce_only=False, entry_state="S1")
    base.update(kw)
    return EntryIntent(**base)


def test_clean_intent_is_approved_with_rounded_qty():
    v = assess(intent(), inputs(), CFG)
    assert v.kind == "APPROVE" and v.reasons == [] and v.qty == Decimal("0.001")   # 80/78000 → step'e aşağı


def test_reject_reasons_follow_catalog_order():
    v = assess(intent(), inputs(kill_switch=True, reconciled=False, stale={"public": True, "market": False}), CFG)
    assert v.kind == "REJECT" and v.reasons[:3] == ["K1_kill_switch", "K2_reconciliation", "K4_stale:public"]


def test_each_check_rejects():
    cases = {
        "K3_warmup": inputs(warmup_bars={"BTCUSDT": 10}),
        "K5_clock_skew": inputs(skew_ms=5000),
        "K6_max_positions": inputs(open_positions={f"p{i}": "X" for i in range(5)}),
        "K7_symbol_busy": inputs(open_positions={"p1": "BTCUSDT"}),
        "K10_leverage": inputs(account_leverage={"BTCUSDT": 20}),
        "K11_margin": inputs(available_balance=Decimal("5")),
        "K13_spread": inputs(spread_bps={"BTCUSDT": Decimal("9")}),
        "K15_slippage": inputs(slippage_bps={"BTCUSDT": Decimal("4")}),
        "K16_cooldown": inputs(last_exit_ms={"BTCUSDT": 990_000}),
        "K16_cooldown_loss": inputs(last_exit_ms={"BTCUSDT": 800_000}, last_exit_was_loss={"BTCUSDT": True}),
        "K16_cooldown_stp": inputs(last_stp_ms={"BTCUSDT": 950_000}),
        "K17_order_budget": inputs(orders_left_10s=2),
        "K18_backoff": inputs(last_429_ms=995_000),
        "K18_banned": inputs(banned=True),
    }
    for reason, inp in cases.items():
        v = assess(intent(), inp, CFG)
        assert v.kind == "REJECT" and reason in v.reasons, reason


def test_filters_reject_when_below_minimum():
    v = assess(intent(notional=Decimal("10")), inputs(), CFG)
    assert v.kind == "REJECT" and "K12_filters" in v.reasons


def test_gross_cap_resizes_then_rejects_below_filter():
    v = assess(intent(), inputs(gross_usdt=Decimal("350")), CFG)     # 50 USDT kalıyor → 0.000 BTC → filtre altı
    assert v.kind == "REJECT" and "K8_gross_cap" in v.reasons and "K12_filters" in v.reasons
    v = assess(intent(symbol="ETHUSDT", price=Decimal("2500"), notional=Decimal("80")),
               inputs(filters={"ETHUSDT": Filters(Decimal("0.001"), Decimal("0.001"), Decimal("20"), Decimal("0.01"))}, spread_bps={"ETHUSDT": Decimal("1")},
                      depth_notional={"ETHUSDT": Decimal("5000")}, slippage_bps={"ETHUSDT": Decimal("0.1")}, warmup_bars={"ETHUSDT": 500},
                      betas={"ETHUSDT": Decimal("1")}, account_leverage={"ETHUSDT": 10}, gross_usdt=Decimal("350")), CFG)
    assert v.kind == "RESIZE" and v.qty == Decimal("0.02") and "K8_gross_cap" in v.reasons   # 50 USDT / 2500


def test_beta_cap_counts_direction():
    v = assess(intent(side="short"), inputs(beta_exposure_usdt=Decimal("-280")), CFG)   # short ekleyince |−360| > 300
    assert v.kind in ("RESIZE", "REJECT") and any(r.startswith("K9_beta") for r in v.reasons)
    v = assess(intent(side="long"), inputs(beta_exposure_usdt=Decimal("-280")), CFG)    # long azaltır → OK
    assert v.kind == "APPROVE"


def test_participation_resizes():
    v = assess(intent(), inputs(depth_notional={"BTCUSDT": Decimal("200")}), CFG)   # 80 > 0.2×200=40 → 40 USDT → 0.000 → REJECT
    assert v.kind == "REJECT" and "K14_participation" in v.reasons


def test_exit_intent_bypasses_everything_but_filters():
    inp = inputs(kill_switch=True, reconciled=False, stale={"public": True, "market": True}, open_positions={f"p{i}": "X" for i in range(5)},
                 spread_bps={"BTCUSDT": Decimal("50")}, orders_left_10s=0, banned=True)
    v = assess(intent(reduce_only=True, notional=Decimal("78")), inp, CFG)
    assert v.kind == "APPROVE" and v.reasons == []
    v = assess(intent(reduce_only=True, notional=Decimal("1")), inp, CFG)
    assert v.kind == "REJECT" and v.reasons == ["K12_filters"]


def test_missing_inputs_fail_closed():
    v = assess(intent(symbol="SOLUSDT", price=Decimal("100")), inputs(), CFG)   # filtre/spread/beta yok
    assert v.kind == "REJECT" and "K3_warmup" in v.reasons and "K12_filters" in v.reasons


def test_assess_is_deterministic():
    a = assess(intent(), inputs(gross_usdt=Decimal("100")), CFG)
    b = assess(intent(), inputs(gross_usdt=Decimal("100")), CFG)
    assert a == b


def test_runaway_detector():
    d = RunawayDetector(window_ms=60_000, max_orders=5, max_consecutive_rejects=3)
    for i in range(5):
        assert d.on_order(now_ms=i * 1000) is None
    assert d.on_order(now_ms=5000) == "runaway_orders"
    d2 = RunawayDetector(window_ms=60_000, max_orders=100, max_consecutive_rejects=3)
    d2.on_reject(1); d2.on_reject(2); assert d2.on_reject(3) == "runaway_rejects"
    d2.on_ack(4); assert d2.on_reject(5) is None   # sayaç sıfırlandı
