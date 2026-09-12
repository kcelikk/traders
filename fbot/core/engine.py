"""Saf çekirdek: step(state, event, now_ns) -> (state, commands). ADR 0007."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from fbot.core.beta_tracker import BetaTracker
from fbot.core.commands import BarClosed, PlaceOrder, StalenessChanged
from fbot.core.decision import DecisionConfig, decide_explain
from fbot.core.market import SymbolMarket
from fbot.core.position import Filters, Position, PositionConfig, PositionManager, PosState
from fbot.core.risk import EntryIntent as RiskIntent, RiskConfig, RiskInputs, assess
from fbot.core.state_engine import StateEngineConfig, SymbolStateEngine
from fbot.events import RawEvent


@dataclass(frozen=True)
class CoreConfig:
    bar_ms: int
    staleness_ms: dict[str, int]
    position: PositionConfig | None = None
    filters: dict[str, Filters] = field(default_factory=dict)
    tick_ms: int = 1000
    pending_entry_ttl_ms: int = 60_000   # giriş emri dolum/ret bildirmezse sembol bu süre sonunda serbest kalır
    state_engine: StateEngineConfig | None = None
    beta_ref: str = "BTCUSDT"
    beta_window: int = 240
    beta_min_n: int = 30
    decision: DecisionConfig | None = None
    risk: RiskConfig | None = None
    account: dict = field(default_factory=dict)   # paper/canlı hesap görünümü (bakiye, kaldıraç); I/O kenarından beslenir


@dataclass
class CoreState:
    markets: dict[str, SymbolMarket] = field(default_factory=dict)
    last_recv_ns: dict[str, int] = field(default_factory=dict)   # kategori → son alım
    stale: dict[str, bool] = field(default_factory=dict)
    ctrl_counts: dict[str, int] = field(default_factory=dict)
    positions: dict[str, Position] = field(default_factory=dict)
    market_state_label: dict[str, str] = field(default_factory=dict)
    state_engines: dict[str, SymbolStateEngine] = field(default_factory=dict)
    beta: object = None
    entry_meta: dict = field(default_factory=dict)
    last_exit_ms: dict = field(default_factory=dict)
    last_exit_was_loss: dict = field(default_factory=dict)
    intents_made: int = 0
    intents_rejected: int = 0
    verdicts_total: int = 0
    no_intent: dict = field(default_factory=dict)
    last_verdicts: list = field(default_factory=list)
    pending_entries: dict = field(default_factory=dict)   # sembol → son geçerlilik (ns). TTL ile süpürülür
    kill_switch: bool = False
    reconciled: bool = True
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
                self._sweep_pending(state, now_ns)
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
                cmds += self._route(state, d, now_ns)
        cmds += self._staleness(state, now_ns)
        self._apply_freeze(state)
        return state, cmds

    # ---------------- pozisyonlar (Faz 4)
    def _exec(self, state: CoreState, ev: RawEvent, now_ns: int) -> list:
        try:
            d = json.loads(ev.raw.decode())
        except ValueError:
            state.parse_errors += 1
            return []
        kind = ev.stream
        if kind in ("order_rejected", "order_unknown"):
            # Giriş emri borsaya ulaşmadı ya da sonucu bilinmiyor: sembolü kilitli tutmak sızıntıdır.
            # `unknown` durumunda güvenlik mutabakattadır (K2 kilidi), rezervasyonun kendisi değil.
            # Pozisyon yönetimi kapalı olsa da (`pm is None`) rezervasyon bırakılır.
            sym = d.get("symbol")
            if sym:
                state.pending_entries.pop(sym, None)
            return []
        if self.pm is None:
            return []
        pos = state.positions.get(d.get("pos_id"))
        if kind == "entry_fill":
            d = self._entry_from_meta(state, d)
            sym = d["symbol"]
            f = self.cfg.filters.get(sym)
            if f is None:
                return []   # filtre bilinmeyen sembolde pozisyon yönetilemez (fail-closed)
            pos = Position.new(d["pos_id"], sym, d["side"], f)
            state.positions[pos.pos_id] = pos
            state.pending_entries.pop(sym, None)
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

    @staticmethod
    def _entry_from_meta(state: CoreState, d: dict) -> dict:
        """Dolum olayında sl/tp yoksa, girişi üreten intent'in yüzdelerinden türet (fail-closed: meta yoksa olduğu gibi bırak)."""
        meta = state.entry_meta.pop(d.get("client_id"), None)
        if meta is None:
            return d
        d = dict(d)
        d.setdefault("pos_id", str(d.get("client_id")))
        d.setdefault("symbol", meta["symbol"])
        d.setdefault("side", meta["side"])
        d.setdefault("entry_state", meta["state"])
        px = Decimal(str(d["price"]))
        sl_pct, tp_pct = Decimal(meta["sl_pct"]) / 100, Decimal(meta["tp_pct"]) / 100
        if "sl" not in d:
            d["sl"] = str(px * (1 - sl_pct) if meta["side"] == "long" else px * (1 + sl_pct))
        if "tp" not in d:
            d["tp"] = str(px * (1 + tp_pct) if meta["side"] == "long" else px * (1 - tp_pct))
        return d

    @staticmethod
    def _sweep_pending(state: CoreState, now_ns: int) -> None:
        """Süresi dolan giriş rezervasyonlarını bırakır. Tek silme noktasına güvenmek sızıntı üretiyordu:
        emir reddedilir, `order_rejected` gelmez ya da dolum hiç gelmezse sembol sonsuza kadar kilitli kalıyordu."""
        for sym in [s for s, deadline in state.pending_entries.items() if deadline <= now_ns]:
            del state.pending_entries[sym]

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

    def _route(self, state: CoreState, d: dict, now_ns: int) -> list:
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
                        extra += self._on_bar_state(state, c, m, now_ns)
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

    def _on_bar_state(self, state: CoreState, bar: BarClosed, m: SymbolMarket, now_ns: int) -> list:
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
        if state.beta is None:
            state.beta = BetaTracker(ref=self.cfg.beta_ref, window=self.cfg.beta_window, min_n=self.cfg.beta_min_n)
        state.beta.on_bar(bar.symbol, bar.start_ms, float(bar.close))
        label, feats, cmds = se.on_bar_cmds(row)
        state.market_state_label[bar.symbol] = label
        cmds += self._decide(state, bar, m, se, label, feats, now_ns)
        return cmds

    # ---------------- giriş zinciri (Faz 6): karar → risk → emir
    def _decide(self, state: CoreState, bar: BarClosed, m: SymbolMarket, se: SymbolStateEngine, label: str, feats: dict, now_ns: int) -> list:
        if self.cfg.decision is None or self.cfg.risk is None:
            return []
        sym = bar.symbol
        if m.best_bid is None or m.best_ask is None:
            return []
        spread_bps = Decimal((m.best_ask - m.best_bid) / m.best_ask * 10000) if m.best_ask else None
        has_pos = sym in {p.symbol for p in state.positions.values() if p.state not in (PosState.CLOSED,)} or sym in state.pending_entries
        view = {"symbol": sym, "state": label, "age_bars": se.bars_in_state, "features": feats,
                "best_bid": m.best_bid, "best_ask": m.best_ask, "spread_bps": spread_bps,
                "stale": any(state.stale.values()), "now_ms": bar.end_ms, "next_funding_ms": m.next_funding_ms,
                "bar_end_ms": bar.end_ms, "has_position": has_pos}
        intent, blocked = decide_explain(view, self.cfg.decision)
        if intent is None:
            state.no_intent[blocked] = state.no_intent.get(blocked, 0) + 1
            if blocked not in ("S0_durum_yok", "allowed_cells_bos", "pozisyon_acik"):
                state.verdicts_total += 1
                state.last_verdicts.insert(0, {"n": state.verdicts_total, "t_ms": bar.end_ms, "symbol": sym,
                                               "kind": "NO_INTENT", "reasons": [blocked], "cell": f"{label}/?",
                                               "explain": f"spread={spread_bps} ref={self.cfg.decision.research_spread_bps.get(sym)} yaş={se.bars_in_state} bar"})
                del state.last_verdicts[20:]
            return []
        verdict = assess(RiskIntent(symbol=sym, side=intent.side, notional=intent.notional, price=intent.price,
                                    reduce_only=False, entry_state=label), self._risk_inputs(state, bar, m, spread_bps), self.cfg.risk)
        state.verdicts_total += 1
        state.last_verdicts.insert(0, {"n": state.verdicts_total, "t_ms": bar.end_ms, "symbol": sym, "kind": verdict.kind,
                                       "reasons": verdict.reasons, "cell": intent.cell, "explain": intent.explain})
        del state.last_verdicts[20:]
        if verdict.kind == "REJECT" or verdict.qty is None or verdict.qty <= 0:
            state.intents_rejected += 1
            return []
        state.intents_made += 1
        state.pending_entries[sym] = now_ns + self.cfg.pending_entry_ttl_ms * 1_000_000
        state.entry_meta[intent.client_order_id] = {"symbol": sym, "side": intent.side, "sl_pct": str(intent.sl_pct),
                                                    "tp_pct": str(intent.tp_pct), "state": label, "cell": intent.cell, "explain": intent.explain}
        return [PlaceOrder(sym, "BUY" if intent.side == "long" else "SELL", "MARKET", verdict.qty, None, False, intent.client_order_id, None)]

    @staticmethod
    def _betas(state: CoreState, symbol: str) -> dict:
        """K9 girdisi: beta float üretir, risk Decimal ile çalışır."""
        if state.beta is None:
            return {}
        b = state.beta.beta(symbol)
        return {symbol: Decimal(str(round(b, 6)))} if b is not None else {}

    def _risk_inputs(self, state: CoreState, bar: BarClosed, m: SymbolMarket, spread_bps) -> RiskInputs:
        acc = self.cfg.account or {}
        lev_view = acc.get("leverage") or {}
        if acc.get("paper") and not lev_view:
            # paper: borsa yok, kaldıraç görünümü config'in kendisidir (canlıda borsadan okunur)
            lev_view = {bar.symbol: self.cfg.risk.leverage.get(bar.symbol, self.cfg.risk.default_leverage)}
        open_pos = {pid: p.symbol for pid, p in state.positions.items() if p.state not in (PosState.CLOSED,)}
        gross = sum((p.qty * (p.entry_price or Decimal(0))) for p in state.positions.values() if p.state not in (PosState.CLOSED,))
        warm = {s: len(se.bars) for s, se in state.state_engines.items()}
        return RiskInputs(kill_switch=state.kill_switch, reconciled=state.reconciled, warmup_bars=warm,
                          stale=dict(state.stale), skew_ms=acc.get("skew_ms", 0), open_positions=open_pos,
                          pending_entries=set(state.pending_entries), gross_usdt=gross, beta_exposure_usdt=Decimal(0),
                          betas=self._betas(state, bar.symbol), account_leverage=lev_view,
                          available_balance=Decimal(str(acc["available_balance"])) if acc.get("available_balance") is not None else None,
                          filters=self.cfg.filters, spread_bps={bar.symbol: spread_bps} if spread_bps is not None else {},
                          depth_notional={}, slippage_bps={bar.symbol: Decimal(0)}, last_exit_ms=state.last_exit_ms,
                          last_exit_was_loss=state.last_exit_was_loss, last_stp_ms={},
                          orders_left_10s=acc.get("orders_left_10s", 100), orders_left_1m=acc.get("orders_left_1m", 500),
                          last_429_ms=acc.get("last_429_ms"), banned=bool(acc.get("banned")), now_ms=bar.end_ms)

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
