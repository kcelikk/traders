import json

from fbot.core.commands import BarClosed, StalenessChanged
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.events import RawEvent

CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000})


def frame(seq, recv_ns, stream, data, cat="market"):
    raw = json.dumps({"stream": stream, "data": data}).encode()
    return RawEvent(seq, recv_ns, seq, cat, stream, raw)


def ctrl(seq, recv_ns, kind, info):
    return RawEvent(seq, recv_ns, seq, "ctrl", kind, json.dumps(info).encode())


def test_engine_routes_and_emits_bars():
    eng, st = Engine(CFG), CoreState()
    t = 1_000_000_000_000  # ns
    st, c1 = eng.step(st, frame(1, t, "btcusdt@aggTrade", {"e": "aggTrade", "s": "BTCUSDT", "a": 1, "p": "10", "q": "1", "T": 60_000, "E": 1}), t)
    st, c2 = eng.step(st, frame(2, t + 1, "btcusdt@aggTrade", {"e": "aggTrade", "s": "BTCUSDT", "a": 2, "p": "11", "q": "1", "T": 120_000, "E": 1}), t + 1)
    assert c1 == [] and len(c2) == 1 and isinstance(c2[0], BarClosed) and c2[0].symbol == "BTCUSDT"
    assert st.markets["BTCUSDT"].last_price is not None


def test_staleness_uses_recv_time_per_category():
    eng, st = Engine(CFG), CoreState()
    t = 10**12
    st, _ = eng.step(st, frame(1, t, "btcusdt@aggTrade", {"e": "aggTrade", "s": "BTCUSDT", "a": 1, "p": "10", "q": "1", "T": 1, "E": 1}), t)
    st, _ = eng.step(st, frame(2, t, "btcusdt@bookTicker", {"e": "bookTicker", "s": "BTCUSDT", "u": 1, "b": "1", "B": "1", "a": "2", "A": "1", "T": 1, "E": 1}, cat="public"), t)
    # 31 s sonra yalnızca market'ten olay: public bayat
    t2 = t + 31_000 * 10**6
    st, cmds = eng.step(st, frame(3, t2, "btcusdt@aggTrade", {"e": "aggTrade", "s": "BTCUSDT", "a": 2, "p": "10", "q": "1", "T": 2, "E": 1}), t2)
    stale = [c for c in cmds if isinstance(c, StalenessChanged)]
    assert stale == [StalenessChanged(category="public", stale=True, age_ms=31_000)]
    # public'ten olay gelince geri döner
    st, cmds = eng.step(st, frame(4, t2, "btcusdt@bookTicker", {"e": "bookTicker", "s": "BTCUSDT", "u": 2, "b": "1", "B": "1", "a": "2", "A": "1", "T": 1, "E": 1}, cat="public"), t2)
    assert [c for c in cmds if isinstance(c, StalenessChanged)] == [StalenessChanged(category="public", stale=False, age_ms=0)]


def test_ctrl_events_are_accepted_and_counted():
    eng, st = Engine(CFG), CoreState()
    st, cmds = eng.step(st, ctrl(1, 10**12, "connect", {"cat": "public"}), 10**12)
    assert cmds == [] and st.ctrl_counts["connect"] == 1


def test_step_is_replayable_bit_equal():
    from fbot.core.commands import canonical
    evs = [frame(i, 10**12 + i, "btcusdt@aggTrade", {"e": "aggTrade", "s": "BTCUSDT", "a": i, "p": str(10 + i % 3), "q": "1", "T": i * 40_000, "E": 1}) for i in range(1, 30)]
    def run():
        eng, st = Engine(CFG), CoreState()
        out = []
        for ev in evs:
            st, cmds = eng.step(st, ev, ev.recv_ns)
            out += [canonical(c) for c in cmds]
        return out
    assert run() == run() and len(run()) > 0
