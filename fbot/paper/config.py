"""Paper config yükleyici: recorder ayarları + çekirdek/karar/risk/pozisyon parametreleri. Doğrulama fail-closed."""
from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from fbot.config import RecorderConfig, load_recorder_config
from fbot.core.cost_drift import CostDriftConfig
from fbot.core.decision import Cell, DecisionConfig
from fbot.core.engine import CoreConfig
from fbot.core.position import PositionConfig
from fbot.core.risk import RiskConfig
from fbot.core.state_engine import StateEngineConfig


class PaperConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionConfig:
    """Emir gönderim yolu (Gate 2.1). `legacy` geri alma yoludur: gönderim olay yolunda, senkron."""
    transport: str = "legacy"          # legacy | persistent_async
    connect_timeout_ms: int = 2000
    read_timeout_ms: int = 5000
    queue_max: int = 256
    reserve_slots: int = 8


@dataclass(frozen=True)
class ReconcileConfig:
    """Sahipsiz koruma emri temizliği ve korumasız pozisyon onarımı. `dry_run`: yalnız plan
    raporlanır, borsaya dokunulmaz. `apply` gözlem sonrası ve proje sahibi onayıyla açılır (ADR 0020)."""
    orphan_cancel: str = "dry_run"     # dry_run | apply
    protect_repair: str = "dry_run"    # dry_run | apply


@dataclass(frozen=True)
class UserDataConfig:
    """User data akışı (Gate 3). `mode="shadow"`: çerçeveler yalnız kayda yazılır, çekirdek tüketmez.
    Geri alma: `enabled = false` → sistem Gate 2 davranışına döner (REST ack tabanlı)."""
    enabled: bool = False
    mode: str = "shadow"               # shadow | active
    stream_base: str = "wss://stream.binancefuture.com"
    keepalive_s: int = 1800            # Binance: key ömrü 60 dk
    jitter_s: int = 60
    seed: int = 0
    staleness_s: int = 3600            # private akış sessizliği: emir yoksa olay da yok


@dataclass(frozen=True)
class PaperConfig:
    recorder: RecorderConfig
    core: CoreConfig
    sim_latency_ms: int
    sim_seed: int
    sim_jitter_ms: int = 0
    sim_partial_timeout_ms: int | None = None
    sim_prob_fill_on_touch: float = 0.0
    sim_book_levels: int = 20
    cost_drift: CostDriftConfig | None = None
    strategy_id: str | None = None        # [run] bölümünden; Gate 5'te strateji kaydı bunu doldurur
    strategy_version: str | None = None
    execution: ExecutionConfig = None
    userdata: UserDataConfig = None
    reconcile: ReconcileConfig = None


def _dec(v):
    return None if v is None else Decimal(str(v))


def load_paper_config(path: str | Path) -> tuple[PaperConfig, str]:
    path = Path(path)
    data = path.read_bytes()
    h = hashlib.sha256(data).hexdigest()[:12]
    t = tomllib.loads(data.decode())
    rec, _ = load_recorder_config(path)
    for sec in ("core", "state_engine", "decision", "position", "risk", "sim", "account"):
        if sec not in t:
            raise PaperConfigError(f"[{sec}] bölümü eksik")
    se = StateEngineConfig(**t["state_engine"])
    d, pos, risk = t["decision"], t["position"], t["risk"]

    cells = tuple(Cell(state=c["state"], dir=c["dir"], h=int(c["h"])) for c in d.get("allowed_cells", []))
    sl = {k: Decimal(str(v)) for k, v in (d.get("sl_pct") or {}).items()}
    tp = {k: Decimal(str(v)) for k, v in (d.get("tp_pct") or {}).items()}
    for c in cells:
        if c.state not in sl or c.state not in tp:
            raise PaperConfigError(f"allowed_cells {c.key()} için sl_pct/tp_pct tanımlı değil (fail-closed)")
    lev = {k: int(v) for k, v in (risk.get("leverage") or {}).items()}
    for sym, v in lev.items():
        if v not in (5, 10):
            raise PaperConfigError(f"kaldıraç {sym}={v}: kilitli karar 5x veya 10x (ADR 0004)")
    if int(risk.get("default_leverage", 5)) not in (5, 10):
        raise PaperConfigError("kaldıraç default_leverage: kilitli karar 5x veya 10x")
    if int(risk.get("max_positions", 5)) > 5:
        raise PaperConfigError("max_positions > 5: kilitli karar (en fazla 5)")

    dcfg = DecisionConfig(allowed_cells=cells, notional_usdt=Decimal(str(d["notional_usdt"])),
                          max_state_age_bars=d.get("max_state_age_bars"), spread_mult=Decimal(str(d["spread_mult"])),
                          research_spread_bps={k: Decimal(str(v)) for k, v in (d.get("research_spread_bps") or {}).items()},
                          funding_guard_ms=d.get("funding_guard_ms"), sl_pct=sl, tp_pct=tp, report_hash=d.get("report_hash"),
                          strategy_tag=str(d.get("strategy_tag", "f0")))
    pcfg = PositionConfig(t_protect_ms=int(pos["t_protect_ms"]), t_backup_ms=int(pos["t_backup_ms"]),
                          working_type=pos["working_type"], price_protect=bool(pos["price_protect"]),
                          min_replace_interval_ms=int(pos["min_replace_interval_ms"]),
                          taker_fee_pct=Decimal(str(pos["taker_fee_pct"])), maker_fee_pct=Decimal(str(pos["maker_fee_pct"])),
                          max_hold_ms=pos.get("max_hold_ms"), lock_trigger_pct=_dec(pos.get("lock_trigger_pct")),
                          lock_offset_pct=_dec(pos.get("lock_offset_pct")), trail_step_pct=_dec(pos.get("trail_step_pct")),
                          trail_gap_pct=_dec(pos.get("trail_gap_pct")), tp1_pct=_dec(pos.get("tp1_pct")), tp1_frac=_dec(pos.get("tp1_frac")),
                          degrade_map={k: set(v) for k, v in (pos.get("degrade_map") or {}).items()} or None)
    rcfg = RiskConfig(max_positions=int(risk.get("max_positions", 5)), gross_cap_usdt=_dec(risk.get("gross_cap_usdt")),
                      beta_cap_usdt=_dec(risk.get("beta_cap_usdt")), leverage=lev, default_leverage=int(risk.get("default_leverage", 5)),
                      margin_buffer=Decimal(str(risk.get("margin_buffer", "0.2"))), spread_max_bps=_dec(risk.get("spread_max_bps")),
                      participation_max=_dec(risk.get("participation_max")), slippage_max_bps=_dec(risk.get("slippage_max_bps")),
                      cooldown_ms=risk.get("cooldown_ms"), cooldown_loss_ms=risk.get("cooldown_loss_ms"), cooldown_stp_ms=risk.get("cooldown_stp_ms"),
                      reserve_orders=int(risk.get("reserve_orders", 3)), backoff_ms=int(risk.get("backoff_ms", 10000)),
                      skew_max_ms=risk.get("skew_max_ms"), warmup_bars=int(risk.get("warmup_bars", 480)))
    core = CoreConfig(bar_ms=int(t["core"]["bar_ms"]), staleness_ms={k: int(v * 1000) for k, v in rec.staleness_s.items()},
                      position=pcfg, filters={}, tick_ms=rec.tick_ms, state_engine=se, decision=dcfg, risk=rcfg,
                      account=dict(t["account"]),
                      pending_entry_ttl_ms=int(t["core"].get("pending_entry_ttl_ms", 60_000)))
    cd = t.get("cost_drift")
    drift = CostDriftConfig(window_ms=int(cd["window_ms"]), capital_usdt=Decimal(str(cd["capital_usdt"])),
                            commission_to_gross_max=_dec(cd.get("commission_to_gross_max")),
                            cost_to_capital_max=_dec(cd.get("cost_to_capital_max")),
                            net_per_trade_min=_dec(cd.get("net_per_trade_min")),
                            min_trades=int(cd.get("min_trades", 10))) if cd else None
    ex = t.get("execution") or {}
    transport = str(ex.get("transport", "legacy"))
    if transport not in ("legacy", "persistent_async"):
        raise PaperConfigError(f"[execution] transport 'legacy' veya 'persistent_async' olmalı: {transport!r}")
    ecfg = ExecutionConfig(transport=transport,
                           connect_timeout_ms=int(ex.get("connect_timeout_ms", 2000)),
                           read_timeout_ms=int(ex.get("read_timeout_ms", 5000)),
                           queue_max=int(ex.get("queue_max", 256)),
                           reserve_slots=int(ex.get("reserve_slots", 8)))
    if ecfg.reserve_slots >= ecfg.queue_max:
        raise PaperConfigError("[execution] reserve_slots < queue_max olmalı (rezerv kuyruğu yutamaz)")
    rc_sec = t.get("reconcile") or {}
    oc = str(rc_sec.get("orphan_cancel", "dry_run"))
    if oc not in ("dry_run", "apply"):
        raise PaperConfigError(f"[reconcile] orphan_cancel 'dry_run' veya 'apply' olmalı: {oc!r}")
    pr = str(rc_sec.get("protect_repair", "dry_run"))
    if pr not in ("dry_run", "apply"):
        raise PaperConfigError(f"[reconcile] protect_repair 'dry_run' veya 'apply' olmalı: {pr!r}")
    rccfg = ReconcileConfig(orphan_cancel=oc, protect_repair=pr)
    ud = t.get("userdata") or {}
    ud_mode = str(ud.get("mode", "shadow"))
    if ud_mode not in ("shadow", "active"):
        raise PaperConfigError(f"[userdata] mode 'shadow' veya 'active' olmalı: {ud_mode!r}")
    ucfg = UserDataConfig(enabled=bool(ud.get("enabled", False)), mode=ud_mode,
                          stream_base=str(ud.get("stream_base", "wss://stream.binancefuture.com")),
                          keepalive_s=int(ud.get("keepalive_s", 1800)), jitter_s=int(ud.get("jitter_s", 60)),
                          seed=int(ud.get("seed", 0)), staleness_s=int(ud.get("staleness_s", 3600)))
    if ucfg.keepalive_s >= 3600:
        raise PaperConfigError("[userdata] keepalive_s < 3600 olmalı: listenKey ömrü 60 dakikadır")
    sim = t["sim"]
    book_levels = int(sim.get("book_levels", 20))
    has_depth = any("depth" in x.lower() for x in rec.public_streams + rec.market_streams)
    if book_levels > 0 and not has_depth and rec.profile != "trader_testnet":
        raise PaperConfigError(f"[streams] profile={rec.profile!r} depth içermiyor ama sim.book_levels={book_levels}: "
                               "dolum simülasyonu sessizce bozulur (fail-closed)")
    return PaperConfig(recorder=rec, core=core, sim_latency_ms=int(sim["latency_ms"]), sim_seed=int(sim["seed"]),
                       sim_jitter_ms=int(sim.get("jitter_ms", 0)), sim_partial_timeout_ms=sim.get("partial_timeout_ms"),
                       sim_prob_fill_on_touch=float(sim.get("prob_fill_on_touch", 0.0)),
                       sim_book_levels=book_levels, cost_drift=drift,
                       strategy_id=t["run"].get("strategy_id"), strategy_version=t["run"].get("strategy_version"),
                       execution=ecfg, userdata=ucfg, reconcile=rccfg), h
