"""Açılış / periyodik mutabakat (saf): borsa snapshot'ı tek doğruluk kaynağıdır (docs/design/faz5-risk-engine.md §5)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExchangeSnapshot:
    positions: dict          # sembol → {"side","qty"}
    open_algos: dict         # sembol → {clientAlgoId}
    open_orders: dict        # sembol → {clientOrderId}
    leverage: dict           # sembol → int
    position_mode: str       # ONE_WAY | HEDGE


@dataclass
class ReconcileResult:
    ok: bool
    mismatches: list = field(default_factory=list)
    unprotected: list = field(default_factory=list)   # borsada pozisyon var, koruma emri yok


def reconcile(internal: dict, snap: ExchangeSnapshot, expected_leverage: dict) -> ReconcileResult:
    mism: list[str] = []
    unprotected: list[str] = []
    if snap.position_mode != "ONE_WAY":
        mism.append(f"position_mode:{snap.position_mode}")
    by_sym = {p["symbol"]: (pid, p) for pid, p in internal.get("positions", {}).items()}
    for sym in sorted(set(by_sym) | set(snap.positions)):
        ours = by_sym.get(sym)
        theirs = snap.positions.get(sym)
        if theirs is None:
            mism.append(f"position_missing_on_exchange:{sym}")
            continue
        if ours is None:
            mism.append(f"position_unknown:{sym}:{theirs['side']}:{theirs['qty']}")
            if not snap.open_algos.get(sym):
                unprotected.append(sym)
            continue
        _, p = ours
        if p["side"] != theirs["side"]:
            mism.append(f"side_mismatch:{sym}")
        if p["qty"] != theirs["qty"]:
            mism.append(f"qty_mismatch:{sym}")
        if sym in expected_leverage and snap.leverage.get(sym) != expected_leverage[sym]:
            mism.append(f"leverage_mismatch:{sym}")
        have = snap.open_algos.get(sym, set())
        for aid in sorted(p.get("algos", set())):
            if aid not in have:
                mism.append(f"algo_missing:{sym}:{aid}")
        if not have:
            unprotected.append(sym)
    known_algos = {a for _, p in by_sym.values() for a in p.get("algos", set())}
    for sym in sorted(snap.open_algos):
        if sym in snap.positions and sym in by_sym:
            continue
        for aid in sorted(snap.open_algos[sym]):
            if aid not in known_algos:
                mism.append(f"algo_orphan:{sym}:{aid}")
    return ReconcileResult(ok=not mism, mismatches=mism, unprotected=unprotected)
