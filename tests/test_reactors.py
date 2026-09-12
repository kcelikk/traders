"""Reaktörler (Gate 4a): olay-tetiklemeli çıkış değerlendirmesi, shadow modda.

Bugün çıkış kuralları yalnız saniyede bir tick'te değerlendiriliyor; fiyat hareketi ile karar
arasında 1 saniyeye kadar kuantizasyon var. Shadow dağıtım emir üretmez, yalnız kaydeder.
"""
import json
from decimal import Decimal as D

import pytest

from fbot.core.commands import ShadowIntent, is_shadow
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PosState, PositionConfig
from fbot.core.reactors import ACTIVE, OFF, SHADOW, ReactorConfig, enabled_reactors
from fbot.events import RawEvent

FILT = {"XUSDT": Filters(D("0.001"), D("0.001"), D("5"), D("0.01"))}
PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=D("0.05"), maker_fee_pct=D("0.02"))
T = 10**12


def cfg(mode=SHADOW, enabled=("backup_stop",)):
    return CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}, position=PCFG,
                      filters=FILT, reactors=ReactorConfig(mode=mode, enabled=enabled))


def open_position(eng, st, sl="99.5"):
    fill = {"pos_id": "t0Labc", "symbol": "XUSDT", "side": "long", "price": "100", "qty": "1",
            "sl": sl, "tp": "101"}
    st, _ = eng.step(st, RawEvent(1, T, T, "exec", "entry_fill", json.dumps(fill).encode()), T)
    st.positions["t0Labc"].state = PosState.MANAGED
    return st


def mark(eng, st, price, seq=2, t=None):
    d = {"stream": "xusdt@markPrice@1s", "data": {"e": "markPriceUpdate", "s": "XUSDT", "p": price,
                                                  "r": "0.0001", "T": 10**13, "E": 1}}
    return eng.step(st, RawEvent(seq, t or T, t or T, "market", "xusdt@markPrice@1s", json.dumps(d).encode()), t or T)


def test_unknown_reactor_id_is_a_configuration_error():
    with pytest.raises(ValueError, match="bilinmeyen reactor"):
        enabled_reactors(ReactorConfig(mode=SHADOW, enabled=("sihirli_cikis",)))


def test_off_mode_produces_nothing_and_touches_no_index():
    eng = Engine(cfg(mode=OFF))
    st = open_position(eng, CoreState())
    st, cmds = mark(eng, st, "98")
    assert [c for c in cmds if is_shadow(c)] == [] and st.shadow_intents == 0


def test_shadow_records_the_intent_but_sends_no_order():
    eng = Engine(cfg())
    st = open_position(eng, CoreState())
    st, cmds = mark(eng, st, "99")                       # stop seviyesinin altında
    shadows = [c for c in cmds if isinstance(c, ShadowIntent)]
    assert len(shadows) == 1
    si = shadows[0]
    assert si.reactor_id == "backup_stop" and si.pos_id == "t0Labc" and si.reason == "backup_stop"
    assert si.reference == "MARK" and si.price == D("99")
    assert not [c for c in cmds if type(c).__name__ in ("PlaceOrder", "PlaceAlgo")], "shadow emir üretmez"


def test_no_intent_while_the_price_is_above_the_stop():
    eng = Engine(cfg())
    st = open_position(eng, CoreState())
    st, cmds = mark(eng, st, "100.5")
    assert [c for c in cmds if is_shadow(c)] == []


def test_no_open_position_means_no_work():
    eng = Engine(cfg())
    st, cmds = mark(eng, CoreState(), "1")
    assert cmds == [] and st.by_symbol == {}


def test_closed_position_leaves_the_symbol_index():
    eng = Engine(cfg())
    st = open_position(eng, CoreState())
    assert st.by_symbol == {"XUSDT": {"t0Labc"}}
    st.positions["t0Labc"].state = PosState.CLOSED
    st, _ = eng.step(st, RawEvent(9, T, T, "ctrl", "tick", b'{"n":1}'), T)
    assert st.by_symbol == {}


def test_intents_are_ordered_deterministically():
    eng = Engine(cfg())
    st = open_position(eng, CoreState())
    a = [c for c in mark(eng, st, "99", seq=2)[1] if is_shadow(c)]
    st2 = open_position(Engine(cfg()), CoreState())
    b = [c for c in mark(Engine(cfg()), st2, "99", seq=2)[1] if is_shadow(c)]
    assert [type(c).__name__ for c in a] == [type(c).__name__ for c in b]
    assert [(c.reactor_id, c.pos_id) for c in a] == [(c.reactor_id, c.pos_id) for c in b]


def test_exit_in_flight_blocks_a_second_intent():
    """Gate 3 kilidi reaktör yolunda da geçerli: uçuşta çıkış varken niyet üretilmez."""
    eng = Engine(cfg())
    st = open_position(eng, CoreState())
    st.positions["t0Labc"].exit_in_flight = "t0Labc-X-v1"
    st.positions["t0Labc"].exit_sent_ns = T
    st, cmds = mark(eng, st, "99")
    assert [c for c in cmds if is_shadow(c)] == []


def test_active_mode_is_refused_until_it_is_approved():
    """Yarım implementasyon, hiç implementasyondan tehlikelidir (CLAUDE.md)."""
    eng = Engine(cfg(mode=ACTIVE))
    st = open_position(eng, CoreState())
    with pytest.raises(NotImplementedError, match="onay"):
        mark(eng, st, "99")


def test_shadow_intents_stay_out_of_the_main_hash_chain():
    from fbot.core.commands import canonical
    si = ShadowIntent("backup_stop", "p1", "XUSDT", "backup_stop", "MARK", D("99"), T)
    assert is_shadow(si) and b"ShadowIntent" in canonical(si)
