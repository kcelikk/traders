"""Saf çekirdek: step(state, event, now_ns) -> (state, commands). ADR 0007."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from fbot.core.commands import StalenessChanged
from fbot.core.market import SymbolMarket
from fbot.events import RawEvent


@dataclass(frozen=True)
class CoreConfig:
    bar_ms: int
    staleness_ms: dict[str, int]


@dataclass
class CoreState:
    markets: dict[str, SymbolMarket] = field(default_factory=dict)
    last_recv_ns: dict[str, int] = field(default_factory=dict)   # kategori → son alım
    stale: dict[str, bool] = field(default_factory=dict)
    ctrl_counts: dict[str, int] = field(default_factory=dict)
    events: int = 0
    parse_errors: int = 0
    last_seq: int = 0


class Engine:
    def __init__(self, cfg: CoreConfig):
        self.cfg = cfg

    def step(self, state: CoreState, ev: RawEvent, now_ns: int) -> tuple[CoreState, list]:
        state.events += 1
        state.last_seq = ev.seq
        cmds: list = []
        if ev.cat == "ctrl":
            state.ctrl_counts[ev.stream] = state.ctrl_counts.get(ev.stream, 0) + 1
            if ev.stream == "connect":
                try:
                    cat = json.loads(ev.raw).get("cat")
                except ValueError:
                    cat = None
                if cat in self.cfg.staleness_ms:
                    state.last_recv_ns[cat] = ev.recv_ns
        else:
            state.last_recv_ns[ev.cat] = ev.recv_ns
            try:
                d = json.loads(ev.raw)
                d = d.get("data", d)
            except ValueError:
                state.parse_errors += 1
                d = None
            if d is not None:
                cmds += self._route(state, d)
        cmds += self._staleness(state, now_ns)
        return state, cmds

    def _route(self, state: CoreState, d: dict) -> list:
        e = d.get("e")
        sym = d.get("s")
        if not sym:
            return []
        m = state.markets.get(sym)
        if m is None:
            m = state.markets[sym] = SymbolMarket(sym, self.cfg.bar_ms)
        if e == "aggTrade":
            return m.on_agg_trade(d)
        if e == "bookTicker":
            return m.on_book_ticker(d)
        if e == "markPriceUpdate":
            return m.on_mark_price(d)
        return []  # depthUpdate, forceOrder: Faz 2'de görünüme dahil değil

    def _staleness(self, state: CoreState, now_ns: int) -> list:
        out = []
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
