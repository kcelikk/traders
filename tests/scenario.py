"""Paylaşılan deterministik senaryo: giriş → koruma → çıkış zincirini üreten sentetik akış.

`tests/test_paper_trader.py` ve `tests/test_golden_orders.py` aynı senaryoyu kullanır; senaryo iki
yerde kopyalanırsa golden baseline ile testler farklı şeyi ölçmeye başlar.
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


def depth_levels(px):
    """L2 defter: her iki tarafta 3 seviye, dolum simülasyonu için yeterli derinlik (ADR 0013)."""
    bids = [[f"{px - 0.01 * k:.2f}", "50"] for k in range(1, 4)]
    asks = [[f"{px + 0.01 * k:.2f}", "50"] for k in range(1, 4)]
    return bids, asks


def market_events(n=90):
    out = []
    u = 0
    for i in range(1, n):
        px = 100 + (i % 11) - 5
        out.append(("market", "xusdt@aggTrade", {"e": "aggTrade", "s": "XUSDT", "a": i, "p": str(px), "q": "1", "T": i * 60_000, "E": 1, "m": i % 3 == 0}))
        out.append(("public", "xusdt@bookTicker", {"e": "bookTicker", "s": "XUSDT", "u": i, "b": str(px - 0.01), "B": "5", "a": str(px + 0.01), "A": "5", "E": 1}))
        b, a = depth_levels(px)
        # tam defter: her seferinde önceki seviyeler sıfırlanır ki defter fiyatı izlesin
        clear_b, clear_a = depth_levels(100 + ((i - 1) % 11) - 5)
        out.append(("public", "xusdt@depth@100ms", {"e": "depthUpdate", "s": "XUSDT", "U": u + 1, "u": u + 2, "pu": u,
                                                    "b": [[p, "0"] for p, _ in clear_b] + b, "a": [[p, "0"] for p, _ in clear_a] + a, "E": 1, "T": 1}))
        u += 2
        out.append(("market", "xusdt@markPrice@1s", {"e": "markPriceUpdate", "s": "XUSDT", "p": str(px), "r": "0.0001", "T": 10**13, "E": 1}))
    return out


def snapshot_event(host, trader):
    """Defterin ilk kurulumu: kayıttaki ctrl/snapshot olayının aynısı."""
    # lastUpdateId, ilk diff'in [U, u] aralığında olmalı (Binance kuralı) yoksa defter hiç senkronize olmaz
    body = {"lastUpdateId": 1, "bids": depth_levels(100)[0], "asks": depth_levels(100)[1]}
    raw = json.dumps({"symbol": "XUSDT", "status": 200, "body": body}).encode()
    ev = host.emit("ctrl", "snapshot", raw)
    trader.on_event(ev, host.now)


def live_run(cells, cfg=None):
    """`cfg`: parite kontrolü aynı senaryoyu farklı çekirdek yapılandırmasıyla koşturur."""
    host = Host()
    trader = PaperTrader(Engine(cfg or core_cfg(cells)), SimExecutor(SimConfig(latency_ms=400, seed=1)), host.emit)
    snapshot_event(host, trader)
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


