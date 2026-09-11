"""Pozisyon durum makinesi ve çıkış kuralları (Faz 4). Saf; zaman parametre olarak verilir."""
from decimal import Decimal

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder
from fbot.core.position import Filters, Position, PositionConfig, PositionManager, PosState

MS = 1_000_000
CFG = PositionConfig(
    t_protect_ms=2000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
    min_replace_interval_ms=5000, max_hold_ms=3_600_000,
    lock_trigger_pct=Decimal("0.3"), lock_offset_pct=Decimal("0.05"), trail_step_pct=Decimal("0.2"), trail_gap_pct=Decimal("0.3"),
    tp1_pct=Decimal("0.5"), tp1_frac=Decimal("0.5"),
    taker_fee_pct=Decimal("0.05"), maker_fee_pct=Decimal("0.02"),
)
F_BTC = Filters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), min_notional=Decimal("50"), tick_size=Decimal("0.1"))
F_ALT = Filters(step_size=Decimal("0.01"), min_qty=Decimal("0.01"), min_notional=Decimal("5"), tick_size=Decimal("0.01"))


def open_long(pm, t=0, price="100", qty="1", sl="98", tp="103", filters=F_ALT):
    pos = Position.new("p1", "XUSDT", "long", filters)
    cmds = pm.on_entry_fill(pos, Decimal(price), Decimal(qty), Decimal(sl), Decimal(tp), now_ns=t)
    return pos, cmds


def test_entry_fill_places_sl_and_tp_close_position():
    pm = PositionManager(CFG)
    pos, cmds = open_long(pm)
    assert pos.state == PosState.PROTECTING
    assert [type(c) for c in cmds] == [PlaceAlgo, PlaceAlgo]
    sl, tp = cmds
    assert sl.type == "STOP_MARKET" and sl.side == "SELL" and sl.close_position and sl.trigger_price == Decimal("98")
    assert tp.type == "TAKE_PROFIT_MARKET" and tp.trigger_price == Decimal("103")
    assert sl.client_algo_id == "p1-SL-v1" and tp.client_algo_id == "p1-TP-v1"
    assert all(len(c.client_algo_id) <= 36 for c in cmds)
    assert sl.working_type == "MARK_PRICE" and sl.price_protect is True


def test_two_acks_move_to_managed_and_protect_timeout_emergency():
    pm = PositionManager(CFG)
    pos, _ = open_long(pm)
    assert pm.on_algo_ack(pos, "p1-SL-v1", now_ns=100 * MS) == [] and pos.state == PosState.PROTECTING
    assert pm.on_algo_ack(pos, "p1-TP-v1", now_ns=200 * MS) == [] and pos.state == PosState.MANAGED
    # yeni pozisyon: ACK gelmeden t_protect aşılırsa acil kapatma
    pos2, _ = open_long(pm)
    cmds = pm.on_tick(pos2, now_ns=2001 * MS, mark=Decimal("100"), bid=Decimal("99.9"), ask=Decimal("100.1"), state_label=None)
    assert pos2.state == PosState.EMERGENCY
    assert len(cmds) == 1 and isinstance(cmds[0], PlaceOrder) and cmds[0].reduce_only and cmds[0].type == "MARKET" and cmds[0].side == "SELL"


def managed(pm, **kw):
    pos, _ = open_long(pm, **kw)
    pm.on_algo_ack(pos, "p1-SL-v1", 1); pm.on_algo_ack(pos, "p1-TP-v1", 1)
    return pos


def test_sl_trigger_cancels_tp_and_tp_trigger_cancels_sl():
    pm = PositionManager(CFG)
    pos = managed(pm)
    cmds = pm.on_algo_triggered(pos, "p1-SL-v1", now_ns=5 * MS)
    assert pos.state == PosState.CLOSING and cmds == [CancelAlgo("XUSDT", "p1-TP-v1")]
    pm.on_exit_fill(pos, Decimal("98"), Decimal("1"), now_ns=6 * MS, reason="sl")
    assert pos.state == PosState.CLOSED and pos.exit_reason == "sl"
    pos2 = managed(pm)
    assert pm.on_algo_triggered(pos2, "p1-TP-v1", 5 * MS) == [CancelAlgo("XUSDT", "p1-SL-v1")]


def test_ratchet_places_new_before_cancel_old_and_only_favorable():
    pm = PositionManager(CFG)
    pos = managed(pm)
    # kâr kilidi tetiği: net kâr ≥ %0.3 → SL entry+cost+offset'e taşınır
    t = 10_000 * MS
    cmds = pm.on_tick(pos, t, mark=Decimal("100.5"), bid=Decimal("100.45"), ask=Decimal("100.55"), state_label=None)
    assert [type(c) for c in cmds] == [PlaceAlgo, CancelAlgo]
    assert cmds[0].client_algo_id == "p1-SL-v2" and cmds[1].client_algo_id == "p1-SL-v1"
    new_sl = cmds[0].trigger_price
    assert new_sl > Decimal("100")            # breakeven + maliyet + offset
    # aleyhte hareket: SL geri çekilmez
    cmds = pm.on_tick(pos, t + 6000 * MS, mark=Decimal("100.2"), bid=Decimal("100.15"), ask=Decimal("100.25"), state_label=None)
    assert cmds == []
    # lehte ama min_replace_interval (5 s) içinde: değişiklik yok
    cmds = pm.on_tick(pos, t + 2000 * MS, mark=Decimal("102"), bid=Decimal("101.95"), ask=Decimal("102.05"), state_label=None)
    assert [c for c in cmds if isinstance(c, PlaceAlgo)] == []
    # aralık geçince trail: SL = mark − trail_gap
    cmds = pm.on_tick(pos, t + 20_000 * MS, mark=Decimal("102"), bid=Decimal("101.95"), ask=Decimal("102.05"), state_label=None)
    sl_cmds = [c for c in cmds if isinstance(c, PlaceAlgo)]
    assert sl_cmds and sl_cmds[0].trigger_price > new_sl and sl_cmds[0].client_algo_id.startswith("p1-SL-v")


def test_backup_stop_when_exchange_stop_silent():
    pm = PositionManager(CFG)
    pos = managed(pm)
    t = 100 * MS
    assert pm.on_tick(pos, t, mark=Decimal("97.9"), bid=Decimal("97.85"), ask=Decimal("97.95"), state_label=None) == []  # ilk geçiş: sayaç başlar
    cmds = pm.on_tick(pos, t + 1600 * MS, mark=Decimal("97.9"), bid=Decimal("97.85"), ask=Decimal("97.95"), state_label=None)
    assert any(isinstance(c, PlaceOrder) and c.reduce_only and c.side == "SELL" for c in cmds)
    assert pos.state == PosState.CLOSING and pos.exit_reason == "backup_stop"


def test_partial_reduce_respects_filters():
    pm = PositionManager(CFG)
    pos = managed(pm, qty="1")
    cmds = pm.on_tick(pos, 10_000 * MS, mark=Decimal("100.8"), bid=Decimal("100.75"), ask=Decimal("100.85"), state_label=None)
    red = [c for c in cmds if isinstance(c, PlaceOrder)]
    assert len(red) == 1 and red[0].qty == Decimal("0.5") and red[0].reduce_only and pos.tp1_done
    # BTC: 0.001 BTC pozisyonda %50 → 0.0005 < minQty → pas
    pm2 = PositionManager(CFG)
    pos2 = managed(pm2, price="78000", qty="0.001", sl="77000", tp="80000", filters=F_BTC)
    cmds = pm2.on_tick(pos2, 10_000 * MS, mark=Decimal("78700"), bid=Decimal("78699"), ask=Decimal("78701"), state_label=None)
    assert not any(isinstance(c, PlaceOrder) for c in cmds) and not pos2.tp1_done


def test_timeout_only_when_not_in_profit_and_frozen_is_silent():
    pm = PositionManager(CFG)
    pos = managed(pm)
    t = 3_600_001 * MS
    cmds = pm.on_tick(pos, t, mark=Decimal("100.01"), bid=Decimal("99.99"), ask=Decimal("100.03"), state_label=None)
    assert pos.state == PosState.CLOSING and pos.exit_reason == "timeout"
    pos2 = managed(pm)
    pm.freeze(pos2)
    assert pm.on_tick(pos2, t, mark=Decimal("50"), bid=Decimal("49"), ask=Decimal("51"), state_label=None) == []
    assert pos2.state == PosState.FROZEN


def test_degradation_exit_uses_state_label():
    pm = PositionManager(PositionConfig(**{**CFG.__dict__, "degrade_map": {"S1": {"S2"}}}))
    pos = managed(pm)
    pos.entry_state = "S1"
    cmds = pm.on_tick(pos, 100 * MS, mark=Decimal("100"), bid=Decimal("99.9"), ask=Decimal("100.1"), state_label="S2")
    assert pos.state == PosState.CLOSING and pos.exit_reason == "degradation"
    assert any(isinstance(c, PlaceOrder) and c.reduce_only for c in cmds)


def test_net_unrealized_pnl_includes_costs():
    pm = PositionManager(CFG)
    pos = managed(pm)  # long 1 @100, taker giriş
    net = pm.net_unrealized_pct(pos, mark=Decimal("101"))
    # brüt +1.0%; giriş 0.05 + tahmini çıkış 0.05 = 0.10 → 0.90
    assert net == Decimal("0.90")


def test_entry_qty_survives_close():
    pm = PositionManager(CFG)
    pos, _ = open_long(pm, qty="0.5")
    assert pos.entry_qty == Decimal("0.5")
    pm.on_exit_fill(pos, Decimal("103"), Decimal("0.5"), 1, reason="tp")
    assert pos.qty == 0 and pos.entry_qty == Decimal("0.5")   # maruziyet hesabı için giriş miktarı kalır
