"""Risk Engine — bağımsız, veto yetkili, saf (docs/design/faz5-risk-engine.md).

assess(intent, inputs, cfg) -> Verdict(kind ∈ {APPROVE, REJECT, RESIZE}, reasons[], qty).
Gerekçeler K1…K18 katalog sırasındadır; None parametre = kontrol kapalı; eksik girdi = fail-closed REJECT.
Çıkış niyetleri (reduce_only) yalnızca K12 filtre kontrolünden geçer. Kârlılık gösterilmedi (ADR 0010).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

from fbot.core.position import Filters


@dataclass(frozen=True)
class RiskConfig:
    max_positions: int
    gross_cap_usdt: Decimal | None
    beta_cap_usdt: Decimal | None
    leverage: dict
    default_leverage: int
    margin_buffer: Decimal
    spread_max_bps: Decimal | None
    participation_max: Decimal | None
    slippage_max_bps: Decimal | None
    cooldown_ms: int | None
    cooldown_loss_ms: int | None
    cooldown_stp_ms: int | None
    reserve_orders: int
    backoff_ms: int
    skew_max_ms: int | None
    warmup_bars: int


@dataclass(frozen=True)
class RiskInputs:
    kill_switch: bool
    reconciled: bool
    warmup_bars: dict            # sembol → dolu bar sayısı
    stale: dict                  # kategori → bayat mı
    skew_ms: int | None
    open_positions: dict         # pos_id → sembol
    pending_entries: set         # sembol (kira tablosunun sembol kümesi; K6/K7 girdisi)
    gross_usdt: Decimal
    beta_exposure_usdt: Decimal  # Σ yön × notional × beta
    betas: dict                  # sembol → beta
    account_leverage: dict       # sembol → borsadaki kaldıraç
    available_balance: Decimal | None
    filters: dict                # sembol → Filters
    spread_bps: dict
    depth_notional: dict         # sembol → ±depth_bps içindeki notional
    slippage_bps: dict
    last_exit_ms: dict
    last_exit_was_loss: dict
    last_stp_ms: dict
    orders_left_10s: int | None
    orders_left_1m: int | None
    last_429_ms: int | None
    banned: bool
    now_ms: int
    # ---- Gate 5: kira sahipliği ve strateji bütçesi (hepsi opsiyonel; tek strateji hâlinde etkisiz)
    lease_busy: str | None = None      # sembol bu strateji için neden meşgul; None = boş
    strategy_id: str | None = None     # niyeti üreten strateji (atıf ve iki katmanlı risk)
    strategy_budget: dict = field(default_factory=dict)   # {"max_positions","gross_cap_usdt"}
    strategy_open: int = 0
    strategy_gross_usdt: Decimal = Decimal(0)


@dataclass(frozen=True)
class EntryIntent:
    symbol: str
    side: str            # long | short
    notional: Decimal
    price: Decimal       # miktar hesabı için referans (best ask/bid)
    reduce_only: bool
    entry_state: str | None = None


@dataclass(frozen=True)
class Verdict:
    kind: str
    reasons: list
    qty: Decimal | None


def _qty(notional: Decimal, price: Decimal, f: Filters) -> Decimal:
    return (notional / price // f.step_size) * f.step_size


def assess(intent: EntryIntent, x: RiskInputs, cfg: RiskConfig) -> Verdict:
    reasons: list[str] = []
    sym = intent.symbol
    f = x.filters.get(sym)
    notional = intent.notional
    resized = False

    if not intent.reduce_only:
        if x.kill_switch:
            reasons.append("K1_kill_switch")
        if not x.reconciled:
            reasons.append("K2_reconciliation")
        if x.warmup_bars.get(sym, 0) < cfg.warmup_bars:
            reasons.append("K3_warmup")
        for cat in sorted(x.stale):
            if x.stale[cat]:
                reasons.append(f"K4_stale:{cat}")
        if cfg.skew_max_ms is not None and (x.skew_ms is None or abs(x.skew_ms) > cfg.skew_max_ms):
            reasons.append("K5_clock_skew")
        if len(x.open_positions) + len(x.pending_entries) >= cfg.max_positions:
            reasons.append("K6_max_positions")
        if sym in x.open_positions.values() or sym in x.pending_entries:
            reasons.append("K7_symbol_busy")
        elif x.lease_busy:
            # Aynı semantik, sahibi de söyleniyor: başka stratejinin kirasındaysa da meşgul.
            reasons.append(f"K7_symbol_busy:{x.lease_busy}")
        # Strateji bütçesi **global limitlerin altında** ikinci bir katmandır; global her zaman kazanır.
        b = x.strategy_budget or {}
        if b.get("max_positions") is not None and x.strategy_open >= int(b["max_positions"]):
            reasons.append("K19_strategy_max_positions")
        if b.get("gross_cap_usdt") is not None:
            room = Decimal(str(b["gross_cap_usdt"])) - x.strategy_gross_usdt
            if room < notional:
                reasons.append("K19_strategy_gross_cap")
                notional = max(room, Decimal(0)); resized = True
        if cfg.gross_cap_usdt is not None:
            room = cfg.gross_cap_usdt - x.gross_usdt
            if room < notional:
                reasons.append("K8_gross_cap")
                notional = max(room, Decimal(0)); resized = True
        if cfg.beta_cap_usdt is not None:
            beta = x.betas.get(sym)
            if beta is None:
                reasons.append("K9_beta_unknown")
            else:
                sign = Decimal(1) if intent.side == "long" else Decimal(-1)
                after = x.beta_exposure_usdt + sign * notional * beta
                if abs(after) > cfg.beta_cap_usdt and abs(after) > abs(x.beta_exposure_usdt):
                    # tavana kadar sığan notional
                    room = (cfg.beta_cap_usdt - sign * x.beta_exposure_usdt) / beta if beta != 0 else Decimal(0)
                    reasons.append("K9_beta_cap")
                    notional = max(min(notional, room), Decimal(0)); resized = True
        want_lev = cfg.leverage.get(sym, cfg.default_leverage)
        if x.account_leverage.get(sym) != want_lev:
            reasons.append("K10_leverage")
        if x.available_balance is None or x.available_balance < (notional / want_lev) * (1 + cfg.margin_buffer):
            reasons.append("K11_margin")
    # K12 filtreler (giriş ve çıkış)
    if f is None:
        reasons.append("K12_filters")
        qty = None
    else:
        qty = _qty(notional, intent.price, f)
        if qty < f.min_qty or qty * intent.price < f.min_notional:
            reasons.append("K12_filters")
    if not intent.reduce_only:
        sp = x.spread_bps.get(sym)
        if cfg.spread_max_bps is not None and (sp is None or sp > cfg.spread_max_bps):
            reasons.append("K13_spread")
        if cfg.participation_max is not None:
            dn = x.depth_notional.get(sym)
            if dn is None:
                reasons.append("K14_participation_unknown")
            elif notional > cfg.participation_max * dn:
                reasons.append("K14_participation")
                notional = cfg.participation_max * dn; resized = True
                qty = _qty(notional, intent.price, f) if f else None
                if f and (qty < f.min_qty or qty * intent.price < f.min_notional) and "K12_filters" not in reasons:
                    reasons.append("K12_filters")
        sl = x.slippage_bps.get(sym)
        if cfg.slippage_max_bps is not None and (sl is None or sl > cfg.slippage_max_bps):
            reasons.append("K15_slippage")
        le = x.last_exit_ms.get(sym)
        if le is not None:
            cd = cfg.cooldown_loss_ms if x.last_exit_was_loss.get(sym) and cfg.cooldown_loss_ms is not None else cfg.cooldown_ms
            if cd is not None and x.now_ms - le < cd:
                reasons.append("K16_cooldown_loss" if x.last_exit_was_loss.get(sym) else "K16_cooldown")
        ls = x.last_stp_ms.get(sym)
        if ls is not None and cfg.cooldown_stp_ms is not None and x.now_ms - ls < cfg.cooldown_stp_ms:
            reasons.append("K16_cooldown_stp")
        if x.orders_left_10s is None or x.orders_left_1m is None or min(x.orders_left_10s, x.orders_left_1m) < cfg.reserve_orders:
            reasons.append("K17_order_budget")
        if x.banned:
            reasons.append("K18_banned")
        elif x.last_429_ms is not None and x.now_ms - x.last_429_ms < cfg.backoff_ms:
            reasons.append("K18_backoff")

    # Yumuşak nedenler küçültme üretir, ret değil. Strateji `gross_cap`'i global K8 ile aynı
    # mekaniktir; strateji pozisyon limiti ise K6 gibi serttir.
    SOFT = ("K8_", "K9_beta_cap", "K14_participation", "K19_strategy_gross_cap")
    hard = [r for r in reasons if not r.startswith(SOFT) or r.endswith("unknown")]
    if hard:
        return Verdict("REJECT", list(reasons), None)
    if resized:
        return Verdict("RESIZE", list(reasons), qty)
    return Verdict("APPROVE", list(reasons), qty)


class RunawayDetector:
    """Arıza dedektörü (günlük limit değil): pencerede emir sayısı ya da ardışık ret sayısı eşiği → kill switch tetikleyici."""

    def __init__(self, window_ms: int, max_orders: int, max_consecutive_rejects: int):
        self.window_ms, self.max_orders, self.max_rej = window_ms, max_orders, max_consecutive_rejects
        self.orders: deque = deque()
        self.consecutive_rejects = 0

    def on_order(self, now_ms: int) -> str | None:
        self.orders.append(now_ms)
        while self.orders and now_ms - self.orders[0] > self.window_ms:
            self.orders.popleft()
        return "runaway_orders" if len(self.orders) > self.max_orders else None

    def on_reject(self, now_ms: int) -> str | None:
        self.consecutive_rejects += 1
        return "runaway_rejects" if self.consecutive_rejects >= self.max_rej else None

    def on_ack(self, now_ms: int) -> None:
        self.consecutive_rejects = 0
