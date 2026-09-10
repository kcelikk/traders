"""Faz 6 Decision Engine: D1 ∧ D2 ∧ D3, açıklanabilir intent, ağırlıklı skorlama yok."""
from decimal import Decimal

from fbot.core.decision import Cell, DecisionConfig, decide
from fbot.core.state_engine import StateEngineConfig, SymbolStateEngine

CELLS = (Cell(state="S1", dir="long", h=15), Cell(state="S3", dir="short", h=5))
CFG = DecisionConfig(allowed_cells=CELLS, notional_usdt=Decimal("80"), max_state_age_bars=3, spread_mult=Decimal("2"),
                     research_spread_bps={"BTCUSDT": Decimal("1.0")}, funding_guard_ms=120_000,
                     sl_pct={"S1": Decimal("0.5")}, tp_pct={"S1": Decimal("1.0")}, report_hash="a693aa07")


def view(**kw):
    base = dict(symbol="BTCUSDT", state="S1", age_bars=0, features={"imb_short": 0.3, "ret_short": 0.001},
                best_bid=Decimal("77990"), best_ask=Decimal("78010"), spread_bps=Decimal("1.2"),
                stale=False, now_ms=1_000_000, next_funding_ms=9_000_000, bar_end_ms=999_000, has_position=False)
    base.update(kw)
    return base


def test_approved_intent_is_explainable():
    i = decide(view(), CFG)
    assert i is not None
    assert i.symbol == "BTCUSDT" and i.side == "long" and i.horizon_min == 15
    assert i.notional == Decimal("80") and i.sl_pct == Decimal("0.5") and i.tp_pct == Decimal("1.0")
    assert i.client_order_id == "eBTCUSDT999000L" and len(i.client_order_id) <= 36
    assert i.cell == "S1/long/15" and i.report_hash == "a693aa07"
    assert "D1" in i.explain and "D2" in i.explain and "D3" in i.explain


def test_d1_cell_not_allowed():
    assert decide(view(state="S2"), CFG) is None
    assert decide(view(), DecisionConfig(**{**CFG.__dict__, "allowed_cells": ()})) is None


def test_d2_state_too_old():
    assert decide(view(age_bars=3), CFG) is not None
    assert decide(view(age_bars=4), CFG) is None


def test_d3_spread_and_staleness_and_funding_guard():
    assert decide(view(spread_bps=Decimal("2.0")), CFG) is not None      # 2.0 ≤ 1.0 × 2
    assert decide(view(spread_bps=Decimal("2.1")), CFG) is None
    assert decide(view(stale=True), CFG) is None
    assert decide(view(next_funding_ms=1_100_000), CFG) is None          # funding'e 100 s kaldı < 120 s
    assert decide(view(next_funding_ms=None), CFG) is not None


def test_no_intent_without_sl_tp_fail_closed():
    cfg = DecisionConfig(**{**CFG.__dict__, "sl_pct": {}, "tp_pct": {}})
    assert decide(view(), cfg) is None


def test_no_second_intent_when_position_open():
    assert decide(view(has_position=True), CFG) is None


def test_s3_direction_from_imbalance():
    cfg = DecisionConfig(**{**CFG.__dict__, "sl_pct": {"S3": Decimal("0.4")}, "tp_pct": {"S3": Decimal("0.8")}})
    assert decide(view(state="S3", features={"imb_short": -0.4}), cfg).side == "short"   # hücre S3/short
    assert decide(view(state="S3", features={"imb_short": 0.4}), cfg) is None            # S3/long hücresi izinli değil
    assert decide(view(state="S3", features={"imb_short": 0.0}), cfg) is None            # yön yok


def test_decide_is_pure_and_deterministic():
    a, b = decide(view(), CFG), decide(view(), CFG)
    assert a == b


def test_decide_explain_reports_blocking_condition():
    from fbot.core.decision import decide_explain
    i, why = decide_explain(view(), CFG)
    assert i is not None and why is None
    assert decide_explain(view(state="S2"), CFG)[1] == "D1_hucre_yok"
    assert decide_explain(view(state="S0"), CFG)[1] == "S0_durum_yok"
    assert decide_explain(view(age_bars=9), CFG)[1] == "D2_durum_eski"
    assert decide_explain(view(stale=True), CFG)[1] == "D3_bayat"
    assert decide_explain(view(spread_bps=Decimal("9")), CFG)[1] == "D3_spread"
    assert decide_explain(view(next_funding_ms=1_050_000), CFG)[1] == "D3_funding_guard"
    assert decide_explain(view(has_position=True), CFG)[1] == "pozisyon_acik"
    cfg2 = DecisionConfig(**{**CFG.__dict__, "sl_pct": {}, "tp_pct": {}})
    assert decide_explain(view(), cfg2)[1] == "sl_tp_yok"
    cfg3 = DecisionConfig(**{**CFG.__dict__, "allowed_cells": ()})
    assert decide_explain(view(), cfg3)[1] == "allowed_cells_bos"
    assert decide_explain(view(state="S3", features={"imb_short": 0.0}), CFG)[1] == "yon_yok"


def test_spread_reason_includes_measured_values():
    from fbot.core.decision import decide_explain
    i, why = decide_explain(view(spread_bps=Decimal("9")), CFG)
    assert i is None and why == "D3_spread"
