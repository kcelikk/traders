"""Uçuştaki çıkış kilidi (Gate 3c).

İki `reduceOnly` market emri arka arkaya giderse: ilki pozisyonu kapatır, ikincisi ya `-2022` ile
döner ya da (kapanış ile yarışırsa) ters pozisyon açar. Bir mantıksal çıkış terminal olmadan
ikincisi üretilmez.
"""
from decimal import Decimal as D

from fbot.core.commands import PlaceOrder
from fbot.core.ids import entry_cid
from fbot.core.position import Filters, PosState, Position, PositionConfig, PositionManager

MS = 1_000_000
FILT = Filters(D("0.001"), D("0.001"), D("5"), D("0.01"))
CFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                     min_replace_interval_ms=5000, taker_fee_pct=D("0.05"), maker_fee_pct=D("0.02"),
                     max_hold_ms=1000, exit_ttl_ms=30_000,
                     degrade_map={"S1": {"S4"}})
POS = entry_cid("t0", "XUSDT", 60_000, "long")
T = 10**12


def managed():
    pm = PositionManager(CFG)
    p = Position.new(POS, "XUSDT", "long", FILT)
    pm.on_entry_fill(p, D("100"), D("1"), D("99.5"), D("101"), T, entry_state="S1")
    p.state = PosState.MANAGED
    return pm, p


def test_second_exit_is_not_produced_while_the_first_is_in_flight():
    pm, p = managed()
    first = pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")   # R2 bozulma
    assert [type(c).__name__ for c in first] == ["PlaceOrder"] and p.exit_in_flight
    p.state = PosState.MANAGED                                                  # kural yeniden değerlendirilsin
    again = pm.on_tick(p, T + 11 * 10**9, D("100"), D("100"), D("100"), "S4")
    assert again == [], "uçuşta çıkış varken ikincisi üretilmemeli"


def test_lock_opens_when_the_exit_fills():
    pm, p = managed()
    cmds = pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")
    cid = cmds[0].client_id
    pm.on_exit_fill(p, D("100"), D("1"), T + 11 * 10**9, reason="degradation", client_id=cid)
    assert p.exit_in_flight is None and p.state == PosState.CLOSED


def test_lock_opens_when_the_exit_is_cancelled():
    pm, p = managed()
    cmds = pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")
    pm.on_exit_terminal(p, cmds[0].client_id)
    assert p.exit_in_flight is None


def test_a_terminal_event_for_another_order_does_not_open_the_lock():
    pm, p = managed()
    cmds = pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")
    pm.on_exit_terminal(p, "baska-emir")
    assert p.exit_in_flight == cmds[0].client_id


def test_lock_expires_so_it_cannot_freeze_the_position_forever():
    """Cevap hiç gelmezse kilit sonsuza kadar kalmamalı: pozisyon kapatılamaz hâle gelir."""
    pm, p = managed()
    pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")
    assert pm.exit_locked(p, T + 10 * 10**9 + 29_000 * MS)
    assert not pm.exit_locked(p, T + 10 * 10**9 + 31_000 * MS)


def test_protect_timeout_emergency_exit_also_respects_the_lock():
    pm, p = managed()
    p.state = PosState.PROTECTING
    p.protect_sent_ns = T
    first = pm.on_tick(p, T + 4 * 10**9, D("100"), D("100"), D("100"), "S1")
    assert [type(c).__name__ for c in first] == ["PlaceOrder"] and p.state == PosState.EMERGENCY
    p.state = PosState.PROTECTING
    p.protect_sent_ns = T
    assert pm.on_tick(p, T + 5 * 10**9, D("100"), D("100"), D("100"), "S1") == []


def test_exit_order_carries_the_id_grammar():
    pm, p = managed()
    cmds = pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")
    cid = cmds[0].client_id
    assert cid.startswith(POS) and cid.endswith("-X-v1") and len(cid) <= 36


def test_full_exit_quantity_respects_the_step_filter():
    """Step'e oturmamış miktar `-1111` ile reddedilir ve pozisyon kapatılamaz."""
    pm, p = managed()
    p.qty = D("1.00049")
    cmds = pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")
    assert cmds[0].qty == D("1.000") and cmds[0].qty % FILT.step_size == 0


def test_dust_below_min_qty_is_not_sent_as_an_order():
    """Filtre altı artık market emriyle kapatılamaz; borsa tarafı koruma devrede kalır."""
    pm, p = managed()
    p.qty = D("0.0009")                        # min_qty 0.001 altında
    cmds = pm.on_tick(p, T + 10 * 10**9, D("100"), D("100"), D("100"), "S4")
    assert cmds == [] and p.exit_in_flight is None
    assert p.exit_reason and "filtre_alti" in p.exit_reason


def test_protection_versions_are_restored_from_the_registry():
    """Yeniden başlatmadan sonra sürüm 1'e dönerse yeni clientAlgoId eskisiyle çakışır ve
    borsadaki koruma emri sahipsiz kalır."""
    from fbot.core.ids import algo_cid
    from fbot.core.oms import PROTECTIVE, OrderRegistry

    pm, p = managed()
    reg = OrderRegistry()
    reg.register(algo_cid(POS, "SL", 4), POS, PROTECTIVE, "XUSDT", now_ns=T)
    reg.register(algo_cid(POS, "TP", 2), POS, PROTECTIVE, "XUSDT", now_ns=T)
    fresh = Position.new(POS, "XUSDT", "long", FILT)
    pm.restore_versions(fresh, reg)
    assert fresh.sl_version == 4 and fresh.tp_version == 2
    assert fresh.sl_id.endswith("-SL-v4")


def test_restore_ignores_terminal_and_foreign_orders():
    from fbot.core.ids import algo_cid
    from fbot.core.oms import PROTECTIVE, OrderRegistry

    pm, p = managed()
    reg = OrderRegistry()
    reg.register(algo_cid(POS, "SL", 9), POS, PROTECTIVE, "XUSDT", now_ns=T)
    reg.on_event({"client_algo_id": algo_cid(POS, "SL", 9), "kind": "algo_canceled"})   # terminal
    reg.register("ios_foreign", "baska", PROTECTIVE, "XUSDT", now_ns=T)
    fresh = Position.new(POS, "XUSDT", "long", FILT)
    pm.restore_versions(fresh, reg)
    assert fresh.sl_version == 0, "terminal emir sürüm geri yüklemez"
