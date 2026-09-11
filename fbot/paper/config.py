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
                          funding_guard_ms=d.get("funding_guard_ms"), sl_pct=sl, tp_pct=tp, report_hash=d.get("report_hash"))
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
                      account=dict(t["account"]))
    cd = t.get("cost_drift")
    drift = CostDriftConfig(window_ms=int(cd["window_ms"]), capital_usdt=Decimal(str(cd["capital_usdt"])),
                            commission_to_gross_max=_dec(cd.get("commission_to_gross_max")),
                            cost_to_capital_max=_dec(cd.get("cost_to_capital_max")),
                            net_per_trade_min=_dec(cd.get("net_per_trade_min")),
                            min_trades=int(cd.get("min_trades", 10))) if cd else None
    sim = t["sim"]
    return PaperConfig(recorder=rec, core=core, sim_latency_ms=int(sim["latency_ms"]), sim_seed=int(sim["seed"]),
                       sim_jitter_ms=int(sim.get("jitter_ms", 0)), sim_partial_timeout_ms=sim.get("partial_timeout_ms"),
                       sim_prob_fill_on_touch=float(sim.get("prob_fill_on_touch", 0.0)),
                       sim_book_levels=int(sim.get("book_levels", 20)), cost_drift=drift), h
