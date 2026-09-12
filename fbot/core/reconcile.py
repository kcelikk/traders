"""Açılış / periyodik mutabakat (saf): borsa snapshot'ı tek doğruluk kaynağıdır (docs/design/faz5-risk-engine.md §5)."""
from __future__ import annotations

from dataclasses import dataclass, field

from fbot.core.commands import CancelAlgo
from fbot.core.ids import SEP


@dataclass(frozen=True)
class ExchangeSnapshot:
    positions: dict          # sembol → {"side","qty"}
    open_algos: dict         # sembol → {clientAlgoId}
    open_orders: dict        # sembol → {clientOrderId}
    leverage: dict           # sembol → int
    position_mode: str       # ONE_WAY | HEDGE
    balance: dict = field(default_factory=dict)   # {"wallet","available"} USDT; borsa doğruluğu
    margin: dict = field(default_factory=dict)    # sembol → {"maint","initial"}


@dataclass
class ReconcileResult:
    ok: bool
    mismatches: list = field(default_factory=list)
    unprotected: list = field(default_factory=list)   # borsada pozisyon var, koruma emri yok
    actions: list = field(default_factory=list)       # sahipsiz algo iptalleri (dry-run'da uygulanmaz)
    foreign: list = field(default_factory=list)       # bizim gramerimize uymayan algo'lar: dokunulmaz
    repairs: list = field(default_factory=list)       # korumasız pozisyona koruma emri (dry-run'da uygulanmaz)
    arm_block: str | None = None                      # doluysa emir yolu açılmaz (HEDGE gibi)


def is_ours(client_algo_id: str, tags: set[str]) -> bool:
    """Yalnız **bizim** kimlik gramerimize uyan algo'ya dokunulur (`{tag}{L|S}{hash}-{SL|TP}-v{n}`).
    Hesapta başka bir aracın ya da elle konmuş emirler olabilir; onları iptal etmek borsada
    bizim olmayan bir değişikliktir."""
    head, sep, tail = str(client_algo_id).partition(SEP)
    if not sep or not tail:
        return False
    role = tail.partition(SEP)[0]
    return role in ("SL", "TP") and any(head.startswith(t) for t in tags if t)


def reconcile(internal: dict, snap: ExchangeSnapshot, expected_leverage: dict,
              strategy_tags: set[str] | None = None) -> ReconcileResult:
    """`strategy_tags`: bu koşuya ait kimlik önekleri. Verilmezse hiçbir iptal komutu üretilmez
    (fail-closed: sahibini bilmediğimiz emre dokunmayız)."""
    mism: list[str] = []
    unprotected: list[str] = []
    actions: list = []
    foreign: list[str] = []
    tags = set(strategy_tags or ())
    arm_block = None
    if snap.position_mode != "ONE_WAY":
        mism.append(f"position_mode:{snap.position_mode}")
        # HEDGE'te `positionSide` semantiği değişir: emir yolu **açılmaz**, yalnız kilitlenmez.
        arm_block = f"position_mode={snap.position_mode}: ONE-WAY kilitli karardır (ADR 0004)"
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
                if is_ours(aid, tags):
                    actions.append(CancelAlgo(sym, aid))
                else:
                    foreign.append(f"{sym}:{aid}")
    # Korumasız pozisyon onarımı: yalnız **bizim bildiğimiz** pozisyon için üretilir. Borsada olup
    # bizde olmayan pozisyona koruma seviyesi uyduramayız; o durum kilitli kalır (K2).
    repairs = []
    for sym in unprotected:
        ours_pos = by_sym.get(sym)
        if ours_pos is None:
            continue
        pid, p = ours_pos
        for role, price in (("SL", p.get("sl")), ("TP", p.get("tp"))):
            if price is None:
                continue
            repairs.append({"pos_id": pid, "symbol": sym, "role": role, "trigger_price": str(price),
                            "side": "SELL" if p["side"] == "long" else "BUY"})
    return ReconcileResult(ok=not mism, mismatches=mism, unprotected=unprotected, actions=actions,
                           foreign=foreign, repairs=repairs, arm_block=arm_block)
