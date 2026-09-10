"""Faz 7 paper trader: canlı akış → çekirdek → simüle execution → aynı akışa yazılan exec olayları.

Kapı kriteri (docs/design/faz7-paper-trading.md §4): üretilen kaydın replay'i, canlı koşunun
karar/emir dizisini bit-eşit üretmeli.
"""
import json
from decimal import Decimal

from fbot.core.commands import PlaceAlgo, PlaceOrder, StateChanged, canonical
from fbot.core.decision import Cell, DecisionConfig
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PositionConfig, PosState
from fbot.core.risk import RiskConfig
from fbot.core.state_engine import StateEngineConfig
from fbot.events import RawEvent
from fbot.execution.sim import SimConfig, SimExecutor
from fbot.paper.trader import PaperTrader
from fbot.sequencer import Sequencer

SE = StateEngineConfig(W=5, N_short=2, N_long=3, p_lo=0.2, p_hi=0.8)
FILT = {"XUSDT": Filters(Decimal("0.001"), Decimal("0.001"), Decimal("5"), Decimal("0.01"))}
PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=Decimal("0.05"), maker_fee_pct=Decimal("0.02"),
                      max_hold_ms=3_600_000, lock_trigger_pct=Decimal("0.3"), lock_offset_pct=Decimal("0.05"),
                      trail_step_pct=Decimal("0.1"), trail_gap_pct=Decimal("0.3"))
RCFG = RiskConfig(max_positions=5, gross_cap_usdt=Decimal("400"), beta_cap_usdt=None, leverage={}, default_leverage=5,
                  margin_buffer=Decimal("0.2"), spread_max_bps=Decimal("50"), participation_max=None, slippage_max_bps=None,
                  cooldown_ms=None, cooldown_loss_ms=None, cooldown_stp_ms=None, reserve_orders=3, backoff_ms=10_000,
                  skew_max_ms=None, warmup_bars=0)


def core_cfg(cells):
    d = DecisionConfig(allowed_cells=cells, notional_usdt=Decimal("80"), max_state_age_bars=None, spread_mult=Decimal("10"),
                       research_spread_bps={"XUSDT": Decimal("5")}, funding_guard_ms=None,
                       sl_pct={s: Decimal("0.5") for s in ("S1", "S2", "S3", "S4")},
                       tp_pct={s: Decimal("1.0") for s in ("S1", "S2", "S3", "S4")}, report_hash="test")
    return CoreConfig(bar_ms=60_000, staleness_ms={"market": 30_000, "public": 30_000}, position=PCFG, filters=FILT,
                      tick_ms=1000, state_engine=SE, decision=d, risk=RCFG,
                      account={"available_balance": "1000", "leverage": {"XUSDT": 5}})


class Host:
    """Kaydı ve sıralamayı taklit eder (gerçekte Recorder yapar)."""

    def __init__(self):
        self.seq = Sequencer()
        self.stream: list[RawEvent] = []
        self.now = 10**12

    def emit(self, cat, stream, raw, recv_ns=None, mono_ns=None):
        ev = self.seq.next(recv_ns or self.now, mono_ns or self.now, cat, stream, raw)
        self.stream.append(ev)
        return ev


def market_events(n=90):
    out = []
    for i in range(1, n):
        px = 100 + (i % 11) - 5
        out.append(("market", "xusdt@aggTrade", {"e": "aggTrade", "s": "XUSDT", "a": i, "p": str(px), "q": "1", "T": i * 60_000, "E": 1, "m": i % 3 == 0}))
        out.append(("public", "xusdt@bookTicker", {"e": "bookTicker", "s": "XUSDT", "u": i, "b": str(px - 0.01), "B": "5", "a": str(px + 0.01), "A": "5", "E": 1}))
        out.append(("market", "xusdt@markPrice@1s", {"e": "markPriceUpdate", "s": "XUSDT", "p": str(px), "r": "0.0001", "T": 10**13, "E": 1}))
    return out


def live_run(cells):
    host = Host()
    trader = PaperTrader(Engine(core_cfg(cells)), SimExecutor(SimConfig(latency_ms=400, seed=1)), host.emit)
    for cat, s, d in market_events():
        host.now += 200_000_000       # 200 ms
        ev = host.emit(cat, s, json.dumps({"stream": s, "data": d}).encode())
        trader.on_event(ev, host.now)
        host.now += 100_000_000
        trader.on_tick(host.now)
    return host, trader


def replay(stream, cells):
    """Kaydı yeniden oynatır (sim yok: exec olayları kayıtta)."""
    eng, st = Engine(core_cfg(cells)), CoreState()
    out = []
    for ev in stream:
        st, cmds = eng.step(st, ev, ev.recv_ns)
        out += cmds
    return st, out


def discovered_cells():
    host, _ = live_run(())
    labels = {json.loads(e.raw)["to_state"] for e in host.stream if e.cat == "ctrl" and e.stream == "state_changed"}
    return tuple(Cell(state=s, dir=d, h=15) for s in sorted(labels - {"S0"}) for d in ("long", "short"))


def test_no_cells_means_no_orders_but_states_recorded():
    host, trader = live_run(())
    kinds = {e.stream for e in host.stream if e.cat == "ctrl"}
    assert "state_changed" in kinds
    assert not [e for e in host.stream if e.cat == "exec"]
    assert trader.stats["orders"] == 0


def test_orders_fills_and_protection_are_recorded_as_events():
    cells = discovered_cells()
    host, trader = live_run(cells)
    cmds = [e for e in host.stream if e.cat == "ctrl" and e.stream == "command"]
    execs = [e for e in host.stream if e.cat == "exec"]
    assert cmds and execs, "emir/dolum olayı kaydedilmedi"
    payloads = [json.loads(e.raw) for e in cmds]
    assert any(p["cmd"] == "PlaceOrder" and p["type"] == "MARKET" for p in payloads)
    assert any(e.stream == "entry_fill" for e in execs)
    sl = [p for p in payloads if p["cmd"] == "PlaceAlgo" and p["type"] == "STOP_MARKET"]
    tp = [p for p in payloads if p["cmd"] == "PlaceAlgo" and p["type"] == "TAKE_PROFIT_MARKET"]
    assert sl and tp, "koruma emri yok"
    assert all(p["close_position"] and p["working_type"] == "MARK_PRICE" for p in sl + tp)
    assert any(p["cmd"] == "CancelAlgo" for p in payloads), "tetik sonrası iptal yok"
    assert {e.stream for e in execs} >= {"entry_fill", "algo_ack", "algo_triggered", "exit_fill"}
    assert trader.stats["orders"] > 0 and trader.stats["fills"] > 0


def test_replay_of_paper_stream_is_bit_equal():
    cells = discovered_cells()
    host, trader = live_run(cells)
    _, replayed = replay(host.stream, cells)
    live_cmds = [canonical(c) for c in trader.commands]
    replay_cmds = [canonical(c) for c in replayed]
    assert replay_cmds == live_cmds and live_cmds


def test_positions_reach_managed_and_are_closed_by_protection():
    cells = discovered_cells()
    host, trader = live_run(cells)
    st = trader.engine_state
    assert st.positions, "pozisyon açılmadı"
    states = {p.state for p in st.positions.values()}
    assert states & {PosState.MANAGED, PosState.CLOSING, PosState.CLOSED, PosState.PROTECTING}


def test_two_identical_runs_produce_identical_streams():
    cells = discovered_cells()
    a = live_run(cells)[0].stream
    b = live_run(cells)[0].stream
    assert [(e.seq, e.cat, e.stream, e.raw) for e in a] == [(e.seq, e.cat, e.stream, e.raw) for e in b]


def test_store_receives_decisions_orders_fills_positions(tmp_path):
    from fbot.paper.store import PaperStore
    cells = discovered_cells()
    host = Host()
    store = PaperStore(tmp_path / "p.db", run_id="t1")
    trader = PaperTrader(Engine(core_cfg(cells)), SimExecutor(SimConfig(latency_ms=400, seed=1)), host.emit, store=store)
    for cat, s, d in market_events():
        host.now += 200_000_000
        trader.on_event(host.emit(cat, s, json.dumps({"stream": s, "data": d}).encode()), host.now)
        host.now += 100_000_000
        trader.on_tick(host.now)
    store.flush()
    sm = store.summary()
    assert sm["decisions"] > 0 and sm["approve"] > 0
    assert sm["orders"] > 0 and sm["fills"] > 0
    assert sm["positions_closed"] > 0 and sm["exit_reasons"]
    pos = store.recent_positions(5)
    assert pos and pos[0]["entry_state"] in ("S1", "S2", "S3", "S4")
    assert all(p["net_pct"] is not None for p in pos if p["state"] == "CLOSED")


def test_closed_position_net_uses_exit_price_not_mark(tmp_path):
    from fbot.paper.store import PaperStore
    cells = discovered_cells()
    host = Host()
    store = PaperStore(tmp_path / "n.db", run_id="t2")
    trader = PaperTrader(Engine(core_cfg(cells)), SimExecutor(SimConfig(latency_ms=400, seed=1)), host.emit, store=store)
    for cat, s, d in market_events():
        host.now += 200_000_000
        trader.on_event(host.emit(cat, s, json.dumps({"stream": s, "data": d}).encode()), host.now)
        host.now += 100_000_000
        trader.on_tick(host.now)
    store.flush()
    closed = [p for p in store.recent_positions(50) if p["state"] == "CLOSED"]
    assert closed
    for p in closed:
        assert p["closed_ns"] is not None and p["closed_ns"] >= p["opened_ns"]
        # net = brüt − maliyet; TP çıkışında pozitif, SL çıkışında negatif olmalı
        net = float(p["net_pct"])
        assert (net > 0) == (p["exit_reason"] == "tp"), (p["exit_reason"], net)
