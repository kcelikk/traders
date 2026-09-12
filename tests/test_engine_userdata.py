"""Gate 3c: user data olayları çekirdeğe kayıt üzerinden bağlanır.

Borsa çerçevesi `pos_id` taşımaz, yalnız `clientOrderId`. Eşleme çekirdekteki `OrderRegistry`
üzerinden yapılır; böylece replay'de aynı olay dizisi aynı sonucu verir.
"""
import json
from decimal import Decimal as D

from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.ids import algo_cid, entry_cid, exit_cid
from fbot.core.oms import ACKED, DONE, ENTRY, FILLED, PROTECTIVE, UNKNOWN
from fbot.core.position import Filters, PositionConfig, PosState
from fbot.events import RawEvent

FILT = {"XUSDT": Filters(D("0.001"), D("0.001"), D("5"), D("0.01"))}
PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=D("0.05"), maker_fee_pct=D("0.02"))
CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}, position=PCFG,
                 filters=FILT, order_ack_ttl_ms=30_000)
POS = entry_cid("t0", "XUSDT", 60_000, "long")
T = 10**12


def step(eng, st, kind, payload, t=T, cat="exec"):
    return eng.step(st, RawEvent(1, t, t, cat, kind, json.dumps(payload).encode()), t)


def armed_state(eng):
    """Giriş emri üretilmiş gibi kaydı hazırlar (normalde `_register_orders` yapar)."""
    st = CoreState()
    st.orders.register(POS, POS, ENTRY, "XUSDT", now_ns=T)
    st.entry_meta[POS] = {"symbol": "XUSDT", "side": "long", "sl_pct": "0.5", "tp_pct": "1.0",
                          "state": "S1", "cell": "S1/long/15", "explain": ""}
    st.pending_entries["XUSDT"] = T + 60 * 10**9
    return st


def test_exchange_fill_opens_the_position_without_carrying_pos_id():
    eng = Engine(CFG)
    st = armed_state(eng)
    st, cmds = step(eng, st, "order_fill", {"kind": "order_fill", "client_id": POS, "symbol": "XUSDT",
                                            "price": "100", "qty": "0.8", "cum_qty": "0.8",
                                            "status": "FILLED", "trade_id": 5, "order_id": 9})
    assert POS in st.positions, "kayıt üzerinden pos_id çözülmeliydi"
    p = st.positions[POS]
    assert p.state == PosState.PROTECTING and p.entry_price == D("100") and p.qty == D("0.8")
    assert st.pending_entries == {}, "dolum rezervasyonu bırakmalı"
    assert [type(c).__name__ for c in cmds] == ["PlaceAlgo", "PlaceAlgo"]
    assert st.orders.get(POS).state == FILLED and st.orders.get(POS).order_id == 9
    # Koruma emirleri de kayda girdi
    assert st.orders.role_of(algo_cid(POS, "SL", 1)) == PROTECTIVE


def test_ack_alone_does_not_touch_the_position():
    eng = Engine(CFG)
    st = armed_state(eng)
    st, cmds = step(eng, st, "order_ack", {"kind": "order_ack", "client_id": POS, "symbol": "XUSDT", "status": "NEW"})
    assert cmds == [] and st.positions == {}
    assert st.orders.get(POS).state == ACKED


def test_foreign_order_event_is_ignored():
    """Hesapta başka bir aracın emri olabilir; onun dolumu bizim pozisyonumuz değildir."""
    eng = Engine(CFG)
    st = armed_state(eng)
    st, cmds = step(eng, st, "order_fill", {"kind": "order_fill", "client_id": "ios_foreign", "symbol": "XUSDT",
                                            "price": "100", "qty": "1", "status": "FILLED"})
    assert cmds == [] and st.positions == {}


def test_cancelled_entry_releases_the_symbol():
    eng = Engine(CFG)
    st = armed_state(eng)
    st, _ = step(eng, st, "order_done", {"kind": "order_done", "client_id": POS, "symbol": "XUSDT",
                                         "status": "CANCELED"})
    assert st.pending_entries == {} and st.orders.get(POS).state == DONE


def test_exit_fill_is_routed_to_the_right_position():
    eng = Engine(CFG)
    st = armed_state(eng)
    st, _ = step(eng, st, "order_fill", {"kind": "order_fill", "client_id": POS, "symbol": "XUSDT",
                                         "price": "100", "qty": "0.8", "status": "FILLED"})
    xid = exit_cid(POS, "X", 1)
    st.orders.register(xid, POS, "exit", "XUSDT", now_ns=T, intent_key=f"{POS}:exit")
    st, _ = step(eng, st, "order_fill", {"kind": "order_fill", "client_id": xid, "symbol": "XUSDT",
                                         "price": "101", "qty": "0.8", "status": "FILLED", "reduce_only": True})
    assert st.positions[POS].state == PosState.CLOSED


def test_unknown_execution_marks_the_order_not_the_position():
    eng = Engine(CFG)
    st = armed_state(eng)
    st, _ = step(eng, st, "order_unknown", {"kind": "order_unknown", "client_id": POS, "symbol": "XUSDT",
                                            "needs_reconcile": True})
    assert st.orders.get(POS).state == UNKNOWN and POS in st.orders.unknown
    assert st.positions == {}, "bilinmeyen sonuç pozisyon açmaz; mutabakat çözer"


def test_silent_order_becomes_unknown_on_tick():
    eng = Engine(CFG)
    st = armed_state(eng)
    st, _ = step(eng, st, "tick", {"n": 1}, t=T + 31 * 10**9, cat="ctrl")
    assert st.orders.get(POS).state == UNKNOWN
