import json
from decimal import Decimal

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder, canonical
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PositionConfig, PosState
from fbot.events import RawEvent

PCFG = PositionConfig(t_protect_ms=2000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=Decimal("0.05"), maker_fee_pct=Decimal("0.02"), max_hold_ms=3_600_000)
FILT = {"XUSDT": Filters(Decimal("0.01"), Decimal("0.01"), Decimal("5"), Decimal("0.01"))}
CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}, position=PCFG, filters=FILT, tick_ms=1000)
MS = 1_000_000


def ev(seq, t, cat, stream, payload):
    return RawEvent(seq, t, seq, cat, stream, json.dumps(payload).encode())


def market(seq, t, stream, data):
    return ev(seq, t, "public" if "bookTicker" in stream else "market", stream, {"stream": stream, "data": data})


def run(events):
    eng, st = Engine(CFG), CoreState()
    out = []
    for e in events:
        st, cmds = eng.step(st, e, e.recv_ns)
        out.append(cmds)
    return st, out


def test_exec_entry_fill_creates_position_and_protection():
    t = 10**12
    st, out = run([ev(1, t, "exec", "entry_fill", {"pos_id": "p1", "symbol": "XUSDT", "side": "long", "price": "100", "qty": "1", "sl": "98", "tp": "103"})])
    assert [type(c) for c in out[0]] == [PlaceAlgo, PlaceAlgo]
    assert st.positions["p1"].state == PosState.PROTECTING


def test_tick_runs_rules_with_market_view():
    t = 10**12
    events = [
        ev(1, t, "exec", "entry_fill", {"pos_id": "p1", "symbol": "XUSDT", "side": "long", "price": "100", "qty": "1", "sl": "98", "tp": "103"}),
        ev(2, t + 1, "exec", "algo_ack", {"pos_id": "p1", "client_algo_id": "p1-SL-v1"}),
        ev(3, t + 2, "exec", "algo_ack", {"pos_id": "p1", "client_algo_id": "p1-TP-v1"}),
        market(4, t + 3, "xusdt@markPrice@1s", {"e": "markPriceUpdate", "s": "XUSDT", "p": "97.5", "E": 1}),
        market(5, t + 4, "xusdt@bookTicker", {"e": "bookTicker", "s": "XUSDT", "u": 1, "b": "97.4", "B": "1", "a": "97.6", "A": "1", "E": 1}),
        ev(6, t + 5, "ctrl", "tick", {"n": 1}),
        ev(7, t + 5 + 1600 * MS, "ctrl", "tick", {"n": 2}),
    ]
    st, out = run(events)
    assert out[5] == []                                   # ilk geçiş: sayaç
    assert any(isinstance(c, PlaceOrder) and c.reduce_only for c in out[6])   # yedek stop
    assert st.positions["p1"].exit_reason == "backup_stop"


def test_exit_fill_closes_and_cancels_remaining_algos():
    t = 10**12
    events = [
        ev(1, t, "exec", "entry_fill", {"pos_id": "p1", "symbol": "XUSDT", "side": "short", "price": "100", "qty": "1", "sl": "102", "tp": "97"}),
        ev(2, t + 1, "exec", "algo_triggered", {"pos_id": "p1", "client_algo_id": "p1-TP-v1"}),
        ev(3, t + 2, "exec", "exit_fill", {"pos_id": "p1", "price": "97", "qty": "1"}),
    ]
    st, out = run(events)
    assert out[1] == [CancelAlgo("XUSDT", "p1-SL-v1")]
    assert st.positions["p1"].state == PosState.CLOSED and st.positions["p1"].exit_reason == "tp"


def test_tick_without_market_view_is_noop_and_sequence_is_deterministic():
    t = 10**12
    events = [ev(1, t, "exec", "entry_fill", {"pos_id": "p1", "symbol": "XUSDT", "side": "long", "price": "100", "qty": "1", "sl": "98", "tp": "103"}),
              ev(2, t + 1, "ctrl", "tick", {"n": 1})]
    st, out = run(events)
    assert out[1] == []
    a = [canonical(c) for cmds in run(events)[1] for c in cmds]
    b = [canonical(c) for cmds in run(events)[1] for c in cmds]
    assert a == b and len(a) == 2


def test_staleness_freezes_positions_and_unfreezes():
    t = 10**12
    events = [
        market(1, t, "xusdt@aggTrade", {"e": "aggTrade", "s": "XUSDT", "a": 1, "p": "100", "q": "1", "T": 1, "E": 1}),
        market(2, t, "xusdt@bookTicker", {"e": "bookTicker", "s": "XUSDT", "u": 1, "b": "99", "B": "1", "a": "101", "A": "1", "E": 1}),
        ev(3, t + 1, "exec", "entry_fill", {"pos_id": "p1", "symbol": "XUSDT", "side": "long", "price": "100", "qty": "1", "sl": "98", "tp": "103"}),
        ev(4, t + 2, "exec", "algo_ack", {"pos_id": "p1", "client_algo_id": "p1-SL-v1"}),
        ev(5, t + 3, "exec", "algo_ack", {"pos_id": "p1", "client_algo_id": "p1-TP-v1"}),
        ev(6, t + 31_000 * MS, "ctrl", "tick", {"n": 1}),      # public bayat → FROZEN
        market(7, t + 31_001 * MS, "xusdt@bookTicker", {"e": "bookTicker", "s": "XUSDT", "u": 2, "b": "99", "B": "1", "a": "101", "A": "1", "E": 1}),
    ]
    st, out = run(events)
    assert st.positions["p1"].state == PosState.FROZEN      # market kategorisi hâlâ bayat → donuk kalır
    events.append(market(8, t + 31_002 * MS, "xusdt@aggTrade", {"e": "aggTrade", "s": "XUSDT", "a": 2, "p": "100", "q": "1", "T": 2, "E": 1}))
    st, out = run(events)
    assert st.positions["p1"].state == PosState.MANAGED     # iki kategori de taze → geri döndü
    assert any(getattr(c, "category", None) == "public" and c.stale for c in out[5])
