"""Sembol kirası (Gate 5): `pending_entries`'in genelleştirilmiş hâli, semantiği aynı."""
from fbot.core.lease import LeaseTable

T = 10**12
TTL = 60 * 10**9


def test_one_owner_per_symbol():
    lt = LeaseTable()
    assert lt.acquire("XUSDT", "v1", T, TTL)
    assert not lt.acquire("XUSDT", "v2", T, TTL), "ikinci strateji aynı sembolü alamaz"
    assert lt.owner("XUSDT") == "v1" and lt.conflicts == 1


def test_same_strategy_cannot_take_a_second_lease_either():
    """K7 semantiği: kendi kirasında bile ikinci giriş yok."""
    lt = LeaseTable()
    lt.acquire("XUSDT", "v1", T, TTL)
    assert not lt.acquire("XUSDT", "v1", T, TTL)
    assert lt.conflicts == 0, "kendi kirası çakışma sayılmaz"


def test_unbound_lease_expires():
    """Süresiz kira, Gate 2.0'da kapatılan pending_entries sızıntısının tekrarı olurdu."""
    lt = LeaseTable()
    lt.acquire("XUSDT", "v1", T, TTL)
    assert lt.sweep(T + TTL - 1) == []
    assert lt.sweep(T + TTL) == ["XUSDT"] and lt.owner("XUSDT") is None


def test_bound_lease_does_not_expire():
    """Açık pozisyonun sembolünü serbest bırakmak ikinci girişe kapı açar."""
    lt = LeaseTable()
    lt.acquire("XUSDT", "v1", T, TTL)
    lt.bind("XUSDT", "p1")
    assert lt.sweep(T + 10 * TTL) == [] and lt.owner("XUSDT") == "v1"


def test_release_is_tied_to_the_position():
    lt = LeaseTable()
    lt.acquire("XUSDT", "v1", T, TTL)
    lt.bind("XUSDT", "p1")
    lt.acquire("YUSDT", "v1", T, TTL)
    lt.bind("YUSDT", "p2")
    assert lt.release_position("p1") == ["XUSDT"]
    assert lt.symbols() == {"YUSDT"}


def test_busy_reason_names_the_owner():
    lt = LeaseTable()
    assert lt.busy_for("XUSDT", "v1") is None
    lt.acquire("XUSDT", "v1", T, TTL)
    assert lt.busy_for("XUSDT", "v1") == "giris_ucusta"
    assert lt.busy_for("XUSDT", "v2") == "baska_strateji:v1"
    lt.bind("XUSDT", "p1")
    assert lt.busy_for("XUSDT", "v1") == "pozisyon_acik"


def test_sweep_is_deterministic_in_order():
    lt = LeaseTable()
    for sym in ("ZUSDT", "AUSDT", "MUSDT"):
        lt.acquire(sym, "v1", T, TTL)
    assert lt.sweep(T + TTL) == ["AUSDT", "MUSDT", "ZUSDT"]


# ---- çekirdeğe bağlanışı: kira `pending_entries` ile aynı yaşam döngüsünü izler
import json
from decimal import Decimal as D

from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PosState, PositionConfig
from fbot.events import RawEvent

FILT = {"XUSDT": Filters(D("0.001"), D("0.001"), D("5"), D("0.01"))}
PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=D("0.05"), maker_fee_pct=D("0.02"))
CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}, position=PCFG,
                 filters=FILT, strategy_id="v1_state_cell")


def fill(eng, st, pos_id="t0Labc", t=T):
    d = {"pos_id": pos_id, "symbol": "XUSDT", "side": "long", "price": "100", "qty": "1",
         "sl": "99.5", "tp": "101"}
    return eng.step(st, RawEvent(1, t, t, "exec", "entry_fill", json.dumps(d).encode()), t)


def test_fill_binds_the_lease_to_the_position():
    eng = Engine(CFG)
    st = CoreState()
    st.leases.acquire("XUSDT", "v1_state_cell", T, TTL)
    st, _ = fill(eng, st)
    assert st.leases.leases["XUSDT"].pos_id == "t0Labc"
    st, _ = eng.step(st, RawEvent(2, T, T, "ctrl", "tick", b'{"n":1}'), T + 10 * TTL)
    assert st.leases.owner("XUSDT") == "v1_state_cell", "bağlı kira TTL ile düşmez"


def test_lease_is_released_only_after_protection_is_terminal():
    """Erken bırakılan kira, ilk pozisyonun koruma emirleri borsadayken ikinci girişe kapı açar."""
    eng = Engine(CFG)
    st = CoreState()
    st.leases.acquire("XUSDT", "v1_state_cell", T, TTL)
    st, _ = fill(eng, st)
    pos = st.positions["t0Labc"]
    pos.state = PosState.CLOSED
    st, _ = eng.step(st, RawEvent(3, T, T, "ctrl", "tick", b'{"n":2}'), T + 1)
    assert st.leases.owner("XUSDT") == "v1_state_cell", "koruma emirleri hâlâ açık: kira durur"
    pos.active_algos = set()
    st, _ = eng.step(st, RawEvent(4, T, T, "ctrl", "tick", b'{"n":3}'), T + 2)
    assert st.leases.owner("XUSDT") is None
