"""Pozisyon durum makinesi ve çıkış kuralları (Faz 4, docs/design/faz4-cikis-kurallari.md). Saf; Decimal; zaman parametre.

Kurallar (sabit öncelik): koruma zaman aşımı → R2 durum bozulması → R1 yedek stop → R5 zaman aşımı → R4 kısmi → R3 kâr kilidi.
`None` parametre = kural kapalı. Kârlılık gösterilmedi (ADR 0010); bu modül yalnızca risk mekaniğidir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder
from fbot.core.ids import algo_cid, exit_cid
from fbot.core.rounding import floor_step, trigger_price

MS = 1_000_000
HUNDRED = Decimal(100)


class PosState(Enum):
    ENTRY_SENT = "ENTRY_SENT"
    PROTECTING = "PROTECTING"
    MANAGED = "MANAGED"
    CLOSING = "CLOSING"
    EMERGENCY = "EMERGENCY"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class Filters:
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal
    tick_size: Decimal


@dataclass(frozen=True)
class PositionConfig:
    t_protect_ms: int
    t_backup_ms: int
    working_type: str
    price_protect: bool
    min_replace_interval_ms: int
    taker_fee_pct: Decimal
    maker_fee_pct: Decimal
    max_hold_ms: int | None = None
    lock_trigger_pct: Decimal | None = None
    lock_offset_pct: Decimal | None = None
    trail_step_pct: Decimal | None = None
    trail_gap_pct: Decimal | None = None
    tp1_pct: Decimal | None = None
    tp1_frac: Decimal | None = None
    degrade_map: dict | None = None   # giriş durumu → çıkışa zorlayan durum kümesi


@dataclass
class Position:
    pos_id: str
    symbol: str
    side: str                      # long | short
    filters: Filters
    state: PosState = PosState.ENTRY_SENT
    qty: Decimal = Decimal(0)
    entry_qty: Decimal = Decimal(0)   # ilk dolum miktarı; kapanışta qty sıfırlanır, maruziyet/maliyet bunu kullanır
    entry_price: Decimal | None = None
    entry_time_ns: int | None = None
    entry_is_maker: bool = False
    entry_state: str | None = None
    sl_price: Decimal | None = None
    tp_price: Decimal | None = None
    sl_version: int = 0
    tp_version: int = 0
    acked: set = field(default_factory=set)
    active_algos: set = field(default_factory=set)
    protect_sent_ns: int | None = None
    sl_crossed_ns: int | None = None
    last_replace_ns: int | None = None
    locked: bool = False
    tp1_done: bool = False
    funding_accrued_pct: Decimal = Decimal(0)
    exit_reason: str | None = None
    exit_seq: int = 0
    prev_state: PosState | None = None

    @staticmethod
    def new(pos_id: str, symbol: str, side: str, filters: Filters) -> "Position":
        return Position(pos_id=pos_id, symbol=symbol, side=side, filters=filters)

    @property
    def sl_id(self) -> str:
        return algo_cid(self.pos_id, "SL", self.sl_version)

    @property
    def tp_id(self) -> str:
        return algo_cid(self.pos_id, "TP", self.tp_version)

    @property
    def exit_side(self) -> str:
        return "SELL" if self.side == "long" else "BUY"


class PositionManager:
    def __init__(self, cfg: PositionConfig):
        self.cfg = cfg

    # ---------------- muhasebe
    def gross_pct(self, pos: Position, mark: Decimal) -> Decimal:
        r = (mark / pos.entry_price - 1) * HUNDRED
        return r if pos.side == "long" else -r

    def cost_pct(self, pos: Position) -> Decimal:
        fee_in = self.cfg.maker_fee_pct if pos.entry_is_maker else self.cfg.taker_fee_pct
        return fee_in + self.cfg.taker_fee_pct + pos.funding_accrued_pct   # çıkış tahmini taker

    def net_unrealized_pct(self, pos: Position, mark: Decimal) -> Decimal:
        return self.gross_pct(pos, mark) - self.cost_pct(pos)

    # ---------------- olaylar
    def on_entry_fill(self, pos: Position, price: Decimal, qty: Decimal, sl: Decimal, tp: Decimal, now_ns: int,
                      is_maker: bool = False, entry_state: str | None = None) -> list:
        pos.entry_price, pos.qty, pos.entry_time_ns, pos.entry_is_maker = price, qty, now_ns, is_maker
        pos.entry_qty = qty
        pos.entry_state = entry_state
        tick = pos.filters.tick_size
        pos.sl_price = trigger_price(sl, tick, pos.side, "SL")
        pos.tp_price = trigger_price(tp, tick, pos.side, "TP")
        pos.sl_version = pos.tp_version = 1
        pos.protect_sent_ns = now_ns
        pos.state = PosState.PROTECTING
        pos.active_algos = {pos.sl_id, pos.tp_id}
        return [self._algo(pos, "STOP_MARKET", pos.sl_price, pos.sl_id),
                self._algo(pos, "TAKE_PROFIT_MARKET", pos.tp_price, pos.tp_id)]

    def on_algo_ack(self, pos: Position, client_algo_id: str, now_ns: int) -> list:
        pos.acked.add(client_algo_id)
        if pos.state == PosState.PROTECTING and pos.sl_id in pos.acked and pos.tp_id in pos.acked:
            pos.state = PosState.MANAGED
        return []

    def on_algo_triggered(self, pos: Position, client_algo_id: str, now_ns: int) -> list:
        pos.active_algos.discard(client_algo_id)
        if pos.state in (PosState.CLOSED,):
            return []
        pos.state = PosState.CLOSING
        pos.exit_reason = pos.exit_reason or ("sl" if "-SL-" in client_algo_id else "tp")
        return self._cancel_active(pos)

    def on_exit_fill(self, pos: Position, price: Decimal, qty: Decimal, now_ns: int, reason: str | None = None) -> list:
        if qty >= pos.qty:
            pos.qty = Decimal(0)
            pos.state = PosState.CLOSED
            pos.exit_reason = pos.exit_reason or reason
            return self._cancel_active(pos)
        pos.qty -= qty
        return []

    def freeze(self, pos: Position) -> None:
        if pos.state not in (PosState.CLOSED, PosState.FROZEN):
            pos.prev_state, pos.state = pos.state, PosState.FROZEN

    def unfreeze(self, pos: Position) -> None:
        if pos.state == PosState.FROZEN:
            pos.state = pos.prev_state or PosState.MANAGED

    # ---------------- tick: kurallar
    def on_tick(self, pos: Position, now_ns: int, mark: Decimal, bid: Decimal, ask: Decimal, state_label: str | None) -> list:
        if pos.state == PosState.PROTECTING:
            if pos.protect_sent_ns is not None and now_ns - pos.protect_sent_ns > self.cfg.t_protect_ms * MS:
                pos.state = PosState.EMERGENCY
                pos.exit_reason = "protect_timeout"
                return [self._exit_order(pos, "EM")]
            return []
        if pos.state != PosState.MANAGED:
            return []
        # R2 durum bozulması
        dm = self.cfg.degrade_map
        if dm and pos.entry_state in dm and state_label in dm[pos.entry_state]:
            return self._close(pos, "degradation")
        # R1 yedek stop
        crossed = mark <= pos.sl_price if pos.side == "long" else mark >= pos.sl_price
        if crossed:
            if pos.sl_crossed_ns is None:
                pos.sl_crossed_ns = now_ns
            elif now_ns - pos.sl_crossed_ns > self.cfg.t_backup_ms * MS:
                return self._close(pos, "backup_stop")
            return []
        pos.sl_crossed_ns = None
        net = self.net_unrealized_pct(pos, mark)
        cmds: list = []
        # R5 zaman aşımı (yalnızca kârda değilken)
        if self.cfg.max_hold_ms is not None and pos.entry_time_ns is not None and now_ns - pos.entry_time_ns > self.cfg.max_hold_ms * MS and net <= 0:
            return self._close(pos, "timeout")
        # R4 kısmi azaltma
        if self.cfg.tp1_pct is not None and not pos.tp1_done and net >= self.cfg.tp1_pct:
            q = floor_step(pos.qty * self.cfg.tp1_frac, pos.filters.step_size)
            if q >= pos.filters.min_qty and q * mark >= pos.filters.min_notional:
                pos.tp1_done = True
                pos.exit_seq += 1
                cmds.append(PlaceOrder(pos.symbol, pos.exit_side, "MARKET", q, None, True, exit_cid(pos.pos_id, "TP1", pos.exit_seq), None))
        # R3 kâr kilidi / trail (yalnızca lehte, aralık kısıtlı)
        if self.cfg.lock_trigger_pct is not None and net >= self.cfg.lock_trigger_pct:
            desired = None
            if not pos.locked:
                off = (self.cost_pct(pos) + self.cfg.lock_offset_pct) / HUNDRED
                desired = pos.entry_price * (1 + off) if pos.side == "long" else pos.entry_price * (1 - off)
            elif self.cfg.trail_gap_pct is not None:
                gap = self.cfg.trail_gap_pct / HUNDRED
                cand = mark * (1 - gap) if pos.side == "long" else mark * (1 + gap)
                step_px = pos.entry_price * (self.cfg.trail_step_pct or Decimal(0)) / HUNDRED
                if (pos.side == "long" and cand >= pos.sl_price + step_px) or (pos.side == "short" and cand <= pos.sl_price - step_px):
                    desired = cand
            favorable = desired is not None and ((pos.side == "long" and desired > pos.sl_price) or (pos.side == "short" and desired < pos.sl_price))
            interval_ok = pos.last_replace_ns is None or now_ns - pos.last_replace_ns >= self.cfg.min_replace_interval_ms * MS
            if favorable and interval_ok:
                desired = trigger_price(desired, pos.filters.tick_size, pos.side, "SL")
                old_id = pos.sl_id
                pos.sl_version += 1
                pos.sl_price = desired
                pos.locked = True
                pos.last_replace_ns = now_ns
                pos.active_algos.add(pos.sl_id)
                pos.active_algos.discard(old_id)
                cmds += [self._algo(pos, "STOP_MARKET", desired, pos.sl_id), CancelAlgo(pos.symbol, old_id)]
        return cmds

    # ---------------- yardımcılar
    def _algo(self, pos: Position, typ: str, trigger: Decimal, cid: str) -> PlaceAlgo:
        return PlaceAlgo(pos.symbol, pos.exit_side, typ, trigger, True, self.cfg.working_type, self.cfg.price_protect, cid)

    def _exit_order(self, pos: Position, tag: str) -> PlaceOrder:
        pos.exit_seq += 1
        return PlaceOrder(pos.symbol, pos.exit_side, "MARKET", pos.qty, None, True, exit_cid(pos.pos_id, tag, pos.exit_seq), None)

    def _close(self, pos: Position, reason: str) -> list:
        pos.state = PosState.CLOSING
        pos.exit_reason = reason
        return [self._exit_order(pos, "X")]

    def _cancel_active(self, pos: Position) -> list:
        ids = sorted(pos.active_algos)
        pos.active_algos = set()
        return [CancelAlgo(pos.symbol, i) for i in ids]

