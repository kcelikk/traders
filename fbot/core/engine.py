"""Saf çekirdek: step(state, event, now_ns) -> (state, commands). ADR 0007."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from fbot.core.commands import BarClosed, StalenessChanged
from fbot.core.market import SymbolMarket
from fbot.core.position import Filters, Position, PositionConfig, PositionManager, PosState
from fbot.core.state_engine import StateEngineConfig, SymbolStateEngine
from fbot.events import RawEvent


@dataclass(frozen=True)
class CoreConfig:
    bar_ms: int
    staleness_ms: dict[str, int]
    position: PositionConfig | None = None
    filters: dict[str, Filters] = field(default_factory=dict)
    tick_ms: int = 1000
    state_engine: StateEngineConfig | None = None


@dataclass
class CoreState:
    markets: dict[str, SymbolMarket] = field(default_factory=dict)
    last_recv_ns: dict[str, int] = field(default_factory=dict)   # kategori → son alım
    stale: dict[str, bool] = field(default_factory=dict)
    ctrl_counts: dict[str, int] = field(default_factory=dict)
    positions: dict[str, Position] = field(default_factory=dict)
    market_state_label: dict[str, str] = field(default_factory=dict)
    state_engines: dict[str, SymbolStateEngine] = field(default_factory=dict)
    events: int = 0
    parse_errors: int = 0
    last_seq: int = 0
    last_data: dict | None = None      # son market olayının çözülmüş `data` sözlüğü (tüketiciler yeniden parse etmesin)
    last_staleness_check_ns: int = 0


class Engine:
    def __init__(self, cfg: CoreConfig):
        self.cfg = cfg
        self.pm = PositionManager(cfg.position) if cfg.position else None

    def step(self, state: CoreState, ev: RawEvent, now_ns: int) -> tuple[CoreState, list]:
        state.events += 1
        state.last_seq = ev.seq
        cmds: list = []
        if ev.cat == "ctrl":
            state.ctrl_counts[ev.stream] = state.ctrl_counts.get(ev.stream, 0) + 1
            if ev.stream == "connect":
                try:
                    cat = json.loads(ev.raw.decode()).get("cat")
                except ValueError:
                    cat = None
                if cat in self.cfg.staleness_ms:
                    state.last_recv_ns[cat] = ev.recv_ns
            elif ev.stream == "tick":
                cmds += self._staleness(state, now_ns)
                self._apply_freeze(state)
                cmds += self._tick_positions(state, now_ns)
                return state, cmds
        elif ev.cat == "exec":
            cmds += self._exec(state, ev, now_ns)
        else:
            state.last_recv_ns[ev.cat] = ev.recv_ns
            try:
                d = json.loads(ev.raw.decode())
                d = d.get("data", d)
            except ValueError:
                state.parse_errors += 1
                d = None
            state.last_data = d
            if d is not None:
                cmds += self._route(state, d)
        cmds += self._staleness(state, now_ns)
        self._apply_freeze(state)
        return state, cmds

    # ---------------- pozisyonlar (Faz 4)
    def _exec(self, state: CoreState, ev: RawEvent, now_ns: int) -> list:
        if self.pm is None:
            return []
        try:
            d = json.loads(ev.raw.decode())
        except ValueError:
            state.parse_errors += 1
            return []
        kind = ev.stream
        pos = state.positions.get(d.get("pos_id"))
        if kind == "entry_fill":
            sym = d["symbol"]
            f = self.cfg.filters.get(sym)
            if f is None:
                return []   # filtre bilinmeyen sembolde pozisyon yönetilemez (fail-closed)
            pos = Position.new(d["pos_id"], sym, d["side"], f)
            state.positions[pos.pos_id] = pos
            return self.pm.on_entry_fill(pos, Decimal(d["price"]), Decimal(d["qty"]), Decimal(d["sl"]), Decimal(d["tp"]), now_ns,
                                         is_maker=bool(d.get("is_maker", False)), entry_state=d.get("entry_state"))
        if pos is None:
            return []
        if kind == "algo_ack":
            return self.pm.on_algo_ack(pos, d["client_algo_id"], now_ns)
        if kind == "algo_triggered":
            return self.pm.on_algo_triggered(pos, d["client_algo_id"], now_ns)
        if kind == "exit_fill":
            return self.pm.on_exit_fill(pos, Decimal(d["price"]), Decimal(d["qty"]), now_ns, reason=d.get("reason"))
        return []

    def _apply_freeze(self, state: CoreState) -> None:
        """Herhangi bir kategori bayatsa açık pozisyonlar FROZEN; hepsi tazeyse geri döner."""
        if self.pm is None:
            return
        any_stale = any(state.stale.values())
        for pos in state.positions.values():
            if any_stale:
                self.pm.freeze(pos)
            else:
                self.pm.unfreeze(pos)

    def _tick_positions(self, state: CoreState, now_ns: int) -> list:
        if self.pm is None:
            return []
        out = []
        for pid in sorted(state.positions):
            pos = state.positions[pid]
            if pos.state in (PosState.CLOSED, PosState.FROZEN):
                continue
            m = state.markets.get(pos.symbol)
            if m is None or m.mark_price is None or m.best_bid is None or m.best_ask is None:
                continue   # görünüm eksik: kural değerlendirilmez (koruma borsada)
            out += self.pm.on_tick(pos, now_ns, m.mark_price, m.best_bid, m.best_ask, state.market_state_label.get(pos.symbol))
        return out

    def _route(self, state: CoreState, d: dict) -> list:
        e = d.get("e")
        sym = d.get("s")
        if not sym:
            return []
        m = state.markets.get(sym)
        if m is None:
            m = state.markets[sym] = SymbolMarket(sym, self.cfg.bar_ms)
        if e == "aggTrade":
            out = m.on_agg_trade(d)
            if self.cfg.state_engine is not None:
                extra = []
                for c in out:
                    if isinstance(c, BarClosed):
                        extra += self._on_bar_state(state, c, m)
                out = out + extra
            return out
        if e == "bookTicker":
            return m.on_book_ticker(d)
        if e == "markPriceUpdate":
            prev_T, prev_r = m.next_funding_ms, m.funding_rate
            out = m.on_mark_price(d)
            # funding anı geçti: bir önceki (o ana ait) oran açık pozisyonlara işlenir; long pozitif oranı öder
            if prev_T is not None and m.next_funding_ms is not None and m.next_funding_ms != prev_T and prev_r is not None:
                for pos in state.positions.values():
                    if pos.symbol == sym and pos.state not in (PosState.CLOSED,) and pos.entry_price is not None:
                        pos.funding_accrued_pct += (prev_r if pos.side == "long" else -prev_r) * Decimal(100)
            return out
        return []  # depthUpdate, forceOrder: Faz 2'de görünüme dahil değil

    def _on_bar_state(self, state: CoreState, bar: BarClosed, m: SymbolMarket) -> list:
        """Bar kapanışında durum etiketi (Faz 6). Spread bar kapanışındaki bookTicker'dan."""
        se = state.state_engines.get(bar.symbol)
        if se is None:
            se = state.state_engines[bar.symbol] = SymbolStateEngine(bar.symbol, self.cfg.state_engine)
        spread = None
        if m.best_bid is not None and m.best_ask is not None and m.best_ask > 0:
            spread = float((m.best_ask - m.best_bid) / m.best_ask * 10000)
        row = {"symbol": bar.symbol, "start_ms": bar.start_ms, "end_ms": bar.end_ms, "open": float(bar.open), "high": float(bar.high),
               "low": float(bar.low), "close": float(bar.close), "volume": float(bar.volume), "buy_volume": float(bar.buy_volume),
               "trades": bar.trades, "spread_bps": spread}
        label, _feats, cmds = se.on_bar_cmds(row)
        state.market_state_label[bar.symbol] = label
        return cmds

    def _staleness(self, state: CoreState, now_ns: int) -> list:
        out = []
        # bayat kategori varken geri dönüş gecikmemeli: her olayda kontrol; aksi halde 100 ms aralıkla
        if not any(state.stale.values()) and state.last_staleness_check_ns and now_ns - state.last_staleness_check_ns < 100_000_000:
            return out
        state.last_staleness_check_ns = now_ns
        for cat, thr_ms in self.cfg.staleness_ms.items():
            last = state.last_recv_ns.get(cat)
            if last is None:
                continue
            age_ms = (now_ns - last) // 1_000_000
            is_stale = age_ms > thr_ms
            if is_stale != state.stale.get(cat, False):
                state.stale[cat] = is_stale
                out.append(StalenessChanged(cat, is_stale, age_ms if is_stale else 0))
        return out
