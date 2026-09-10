"""Faz 6: Market State Engine çekirdekte; araştırma koduyla bit-eşit olmalı (ADR/PHASE Faz 6 kriter 1)."""
import json
from decimal import Decimal

from fbot.core.commands import StateChanged, canonical
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.state_engine import StateEngineConfig, SymbolStateEngine
from fbot.events import RawEvent
from fbot.research.features import FeatureConfig, compute_features
from fbot.research.states import StateConfig, label_state

CFG = StateEngineConfig(W=5, N_short=2, N_long=3, p_lo=0.2, p_hi=0.8)


def bars(n, seed=1):
    out, p = [], 100.0
    for i in range(n):
        p *= 1 + ((i * seed % 7) - 3) / 500
        out.append({"symbol": "X", "start_ms": i * 60_000, "end_ms": i * 60_000 + 59_999, "open": p * 0.999, "high": p * 1.002,
                    "low": p * 0.997, "close": p, "volume": 10 + (i % 5), "buy_volume": 5 + (i % 3), "trades": 3, "spread_bps": 1.0 + (i % 3) * 0.1})
    return out


def test_core_labels_match_research_exactly():
    data = bars(60)
    se = SymbolStateEngine("X", CFG)
    core = [se.on_bar(b)[0] for b in data]
    feats = compute_features(data, FeatureConfig(W=CFG.W, N_short=CFG.N_short, N_long=CFG.N_long))
    research = [label_state(f, StateConfig(CFG.p_lo, CFG.p_hi)) for f in feats]
    assert core == research
    assert set(core) - {"S0", "S1", "S2", "S3", "S4"} == set()


def test_core_features_match_research_exactly():
    data = bars(40, seed=3)
    se = SymbolStateEngine("X", CFG)
    core = [se.on_bar(b)[1] for b in data]
    research = compute_features(data, FeatureConfig(W=CFG.W, N_short=CFG.N_short, N_long=CFG.N_long))
    assert core == research


def test_state_changed_command_carries_evidence():
    data = bars(60)
    se = SymbolStateEngine("X", CFG)
    changes = []
    for b in data:
        st, f, cmds = se.on_bar_cmds(b)
        changes += cmds
    assert changes and all(isinstance(c, StateChanged) for c in changes)
    c = changes[0]
    assert c.symbol == "X" and c.to_state != c.from_state and c.bar_end_ms > 0
    assert isinstance(c.evidence, str) and "pct_" in c.evidence
    assert canonical(c).startswith(b"StateChanged|X|")


def test_engine_emits_state_changed_and_tracks_label():
    cfg = CoreConfig(bar_ms=60_000, staleness_ms={"market": 30_000}, state_engine=CFG)
    eng, st = Engine(cfg), CoreState()
    t = 10**12
    seen = []
    for i in range(1, 80):
        raw = json.dumps({"stream": "xusdt@aggTrade", "data": {"e": "aggTrade", "s": "XUSDT", "a": i, "p": str(100 + (i % 9) - 4), "q": "1", "T": i * 60_000, "E": 1, "m": i % 2 == 0}}).encode()
        st, cmds = eng.step(st, RawEvent(i, t + i, i, "market", "xusdt@aggTrade", raw), t + i)
        seen += [c for c in cmds if isinstance(c, StateChanged)]
    assert seen, "durum geçişi üretilmedi"
    assert st.market_state_label["XUSDT"] in ("S0", "S1", "S2", "S3", "S4")
    assert st.market_state_label["XUSDT"] == seen[-1].to_state


def test_no_state_engine_means_no_commands():
    cfg = CoreConfig(bar_ms=60_000, staleness_ms={"market": 30_000})
    eng, st = Engine(cfg), CoreState()
    t = 10**12
    for i in range(1, 10):
        raw = json.dumps({"stream": "xusdt@aggTrade", "data": {"e": "aggTrade", "s": "XUSDT", "a": i, "p": "100", "q": "1", "T": i * 60_000, "E": 1}}).encode()
        st, cmds = eng.step(st, RawEvent(i, t + i, i, "market", "xusdt@aggTrade", raw), t + i)
        assert not [c for c in cmds if isinstance(c, StateChanged)]


def test_window_must_cover_percentile_of_percentile():
    """vol_ratio W bar ister, persentili W bar daha: pencere < 2W ise S3/S4 sessizce kaybolur."""
    se = SymbolStateEngine("X", CFG)
    assert se._keep() >= 2 * CFG.W
    data = bars(200)
    for b in data:
        st, f = se.on_bar(b)
    assert f["pct_vol_ratio"] is not None and f["pct_rv_short"] is not None
