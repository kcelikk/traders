"""Sağlık modeli (Gate 4b): bayatlık kuralları susturmaz, güvenilmez fiyata dayananları durdurur."""
from fbot.core.health import FULL, HALTED, PROTECTION_ONLY, HealthFacts, entry_allowed, exit_mode, view


def facts(**kw):
    return HealthFacts(**{"stale": {"public": False, "market": False}, **kw})


def test_healthy_system_runs_every_rule():
    f = facts()
    assert exit_mode(f) == FULL and entry_allowed(f)


def test_stale_market_stops_price_based_rules_not_everything():
    """Eski davranış: bayatlıkta tüm pozisyonlar FROZEN, koruma zaman aşımı bile susuyordu."""
    f = facts(stale={"public": True, "market": False})
    assert exit_mode(f) == PROTECTION_ONLY
    assert not entry_allowed(f)


def test_unreconciled_state_halts_rule_generated_orders():
    """İç durumun borsayla aynı olduğunu bilmiyorsak, hayalet pozisyona çıkış emri göndermek
    gerçek bir pozisyonu ters çevirebilir. Borsa tarafı koruma yine devrede."""
    assert exit_mode(facts(reconciled=False)) == HALTED
    assert exit_mode(facts(reconciled=False, stale={"market": True})) == HALTED


def test_kill_switch_blocks_entry_but_not_protective_exits():
    f = facts(kill_switch=True)
    assert not entry_allowed(f) and exit_mode(f) == FULL


def test_warmup_blocks_entry_only():
    f = facts(warmup_done=False)
    assert not entry_allowed(f) and exit_mode(f) == FULL


def test_unknown_user_stream_age_is_not_staleness():
    """Emir yoksa user data akışı sessizdir; sessizlik ≠ kopukluk."""
    assert not facts(user_stream_age_s=None, user_stream_limit_s=3600).user_stream_stale
    assert not facts(user_stream_age_s=10, user_stream_limit_s=3600).user_stream_stale
    assert facts(user_stream_age_s=4000, user_stream_limit_s=3600).user_stream_stale


def test_view_separates_facts_from_derived_values():
    v = view(facts(stale={"market": True}))
    assert set(v) == {"facts", "derived"}
    assert v["derived"]["exit_mode"] == PROTECTION_ONLY
    assert v["facts"]["market_stale"] is True and v["facts"]["reconciled"] is True


# ---- çekirdeğe bağlanışı: bayatlıkta hangi kural çalışır, hangisi bekler
import json
from decimal import Decimal as D

from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PosState, Position, PositionConfig, PositionManager
from fbot.events import RawEvent

FILT = Filters(D("0.001"), D("0.001"), D("5"), D("0.01"))
PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=D("0.05"), maker_fee_pct=D("0.02"),
                      max_hold_ms=3_600_000, lock_trigger_pct=D("0.3"), lock_offset_pct=D("0.05"))
T = 10**12


def position(state=PosState.MANAGED):
    pm = PositionManager(PCFG)
    p = Position.new("t0Labc", "XUSDT", "long", FILT)
    pm.on_entry_fill(p, D("100"), D("1"), D("99.5"), D("101"), T, entry_state="S1")
    p.state = state
    return pm, p


def test_protection_timeout_still_fires_while_the_market_is_stale():
    """Korumasız pozisyon bayatlıkta terk edilmez: eski FROZEN davranışı bu kuralı da susturuyordu."""
    pm, p = position(PosState.PROTECTING)
    p.protect_sent_ns = T
    cmds = pm.on_tick(p, T + 4 * 10**9, D("100"), D("99"), D("101"), "S1", mode=PROTECTION_ONLY)
    assert [type(c).__name__ for c in cmds] == ["PlaceOrder"] and p.state == PosState.EMERGENCY


def test_price_based_rules_wait_while_the_market_is_stale():
    pm, p = position()
    p.sl_crossed_ns = T                                   # R1 yedek stop tetiklenmeye hazır
    assert pm.on_tick(p, T + 9 * 10**9, D("98"), D("98"), D("98"), "S1", mode=PROTECTION_ONLY) == []
    cmds = pm.on_tick(p, T + 9 * 10**9, D("98"), D("98"), D("98"), "S1", mode=FULL)
    assert [type(c).__name__ for c in cmds] == ["PlaceOrder"], "taze fiyatta aynı kural çalışmalı"


def test_halted_produces_no_orders_at_all():
    pm, p = position(PosState.PROTECTING)
    p.protect_sent_ns = T
    assert pm.on_tick(p, T + 9 * 10**9, D("100"), D("99"), D("101"), "S1", mode=HALTED) == []


def test_engine_halts_rule_orders_when_not_reconciled():
    cfg = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}, position=PCFG,
                     filters={"XUSDT": FILT})
    eng = Engine(cfg)
    st = CoreState()
    st.reconciled = False
    st, _ = eng.step(st, RawEvent(1, T, T, "exec", "entry_fill",
                                  json.dumps({"pos_id": "t0Labc", "symbol": "XUSDT", "side": "long",
                                              "price": "100", "qty": "1", "sl": "99.5", "tp": "101"}).encode()), T)
    st.positions["t0Labc"].state = PosState.PROTECTING
    st.positions["t0Labc"].protect_sent_ns = T
    st, cmds = eng.step(st, RawEvent(2, T, T, "ctrl", "tick", b'{"n":1}'), T + 9 * 10**9)
    assert cmds == [] and st.exit_mode == HALTED
