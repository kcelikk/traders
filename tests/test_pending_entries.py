"""Giriş rezervasyonu sızıntısı (Gate 2.0).

Eskiden `pending_entries` bir `set`'ti ve tek silme noktası vardı: `entry_fill`. Emir reddedilir,
sonucu bilinmez ya da dolum hiç gelmezse sembol **sonsuza kadar** kilitli kalıyordu; K5 o sembolde
bir daha giriş üretmiyordu.
"""
import json
from decimal import Decimal

from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PositionConfig
from fbot.events import RawEvent

CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}, pending_entry_ttl_ms=5_000)
PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=Decimal("0.05"), maker_fee_pct=Decimal("0.02"))
POS_CFG = CoreConfig(**{**CFG.__dict__, "position": PCFG,
                        "filters": {"XUSDT": Filters(Decimal("0.001"), Decimal("0.001"), Decimal("5"), Decimal("0.01"))}})
T = 10**12


def tick(eng, st, now_ns):
    return eng.step(st, RawEvent(1, now_ns, now_ns, "ctrl", "tick", b'{"n":1}'), now_ns)


def exec_ev(eng, st, kind, payload, now_ns):
    return eng.step(st, RawEvent(2, now_ns, now_ns, "exec", kind, json.dumps(payload).encode()), now_ns)


def test_reservation_expires_after_the_ttl():
    eng, st = Engine(CFG), CoreState()
    st.pending_entries["XUSDT"] = T + 5_000 * 10**6
    st, _ = tick(eng, st, T + 4_000 * 10**6)
    assert set(st.pending_entries) == {"XUSDT"}, "süre dolmadan bırakılmamalı"
    st, _ = tick(eng, st, T + 5_001 * 10**6)
    assert st.pending_entries == {}


def test_rejected_entry_releases_the_symbol_immediately():
    eng, st = Engine(CFG), CoreState()
    st.pending_entries["XUSDT"] = T + 60_000 * 10**6
    st, _ = exec_ev(eng, st, "order_rejected", {"symbol": "XUSDT", "client_id": "f0Labc", "code": -2019}, T)
    assert st.pending_entries == {}


def test_unknown_entry_also_releases_but_reconcile_is_the_guard():
    """`unknown`ta emir gerçekleşmiş olabilir; rezervasyonu tutmak sızıntı, bırakmak güvenli değil.
    Güvenlik mutabakattadır: `needs_reconcile` K2'yi kilitler."""
    eng, st = Engine(CFG), CoreState()
    st.pending_entries["XUSDT"] = T + 60_000 * 10**6
    st, _ = exec_ev(eng, st, "order_unknown", {"symbol": "XUSDT", "client_id": "f0Labc", "needs_reconcile": True}, T)
    assert st.pending_entries == {}


def test_fill_still_clears_the_reservation():
    eng, st = Engine(POS_CFG), CoreState()
    st.pending_entries["XUSDT"] = T + 60_000 * 10**6
    st, _ = exec_ev(eng, st, "entry_fill", {"pos_id": "p1", "symbol": "XUSDT", "side": "long", "price": "100",
                                            "qty": "1", "sl": "99", "tp": "101"}, T)
    assert st.pending_entries == {}


def test_other_symbols_are_untouched_by_the_sweep():
    eng, st = Engine(CFG), CoreState()
    st.pending_entries.update({"AUSDT": T + 1_000 * 10**6, "BUSDT": T + 9_000 * 10**6})
    st, _ = tick(eng, st, T + 2_000 * 10**6)
    assert set(st.pending_entries) == {"BUSDT"}
