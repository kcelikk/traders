"""Decision Engine (Faz 6) — giriş niyeti. Saf; ağırlıklı skorlama yok, en fazla 3 sert koşul (docs/design/faz6-giris-mantigi.md §3).

D1 hücre izinli · D2 durum yeni · D3 yürütme uygun. Hepsi AND. sl/tp yoksa intent üretilmez (fail-closed).
Kârlılık gösterilmedi (ADR 0010): `allowed_cells` boşken bu motor hiçbir intent üretmez.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fbot.research.states import directions


@dataclass(frozen=True)
class Cell:
    state: str
    dir: str
    h: int

    def key(self) -> str:
        return f"{self.state}/{self.dir}/{self.h}"


@dataclass(frozen=True)
class DecisionConfig:
    allowed_cells: tuple
    notional_usdt: Decimal
    max_state_age_bars: int | None
    spread_mult: Decimal
    research_spread_bps: dict
    funding_guard_ms: int | None
    sl_pct: dict
    tp_pct: dict
    report_hash: str | None = None


@dataclass(frozen=True)
class EntryIntent:
    symbol: str
    side: str
    notional: Decimal
    price: Decimal
    horizon_min: int
    sl_pct: Decimal
    tp_pct: Decimal
    entry_state: str
    cell: str
    client_order_id: str
    explain: str
    report_hash: str | None


def decide(v: dict, cfg: DecisionConfig) -> EntryIntent | None:
    return decide_explain(v, cfg)[0]


def decide_explain(v: dict, cfg: DecisionConfig) -> tuple[EntryIntent | None, str | None]:
    """(intent, engelleyen_koşul). Sessiz `None` yerine nedeni de döndürür — gözlemlenebilirlik için."""
    sym, state = v["symbol"], v["state"]
    if v.get("has_position"):
        return None, "pozisyon_acik"
    if not cfg.allowed_cells:
        return None, "allowed_cells_bos"
    if state == "S0":
        return None, "S0_durum_yok"
    # yön: durum kuralından (araştırma kodu), hücre listesiyle kesiştirilir
    dirs = [d for d, _tag in directions(state, v.get("features") or {})]
    if not dirs:
        return None, "yon_yok"
    cell = next((c for c in cfg.allowed_cells if c.state == state and c.dir in dirs), None)
    if cell is None:
        return None, "D1_hucre_yok"
    d1 = f"D1 hücre {cell.key()} izinli"
    # D2: durum yeni girildi
    age = v.get("age_bars")
    if cfg.max_state_age_bars is not None and (age is None or age > cfg.max_state_age_bars):
        return None, "D2_durum_eski"
    d2 = f"D2 durum yaşı {age} bar ≤ {cfg.max_state_age_bars}"
    # D3: yürütme uygunluğu
    if v.get("stale"):
        return None, "D3_bayat"
    sp, ref = v.get("spread_bps"), cfg.research_spread_bps.get(sym)
    if sp is None or ref is None or sp > ref * cfg.spread_mult:
        return None, "D3_spread"
    nf, now = v.get("next_funding_ms"), v["now_ms"]
    if cfg.funding_guard_ms is not None and nf is not None and 0 <= nf - now < cfg.funding_guard_ms:
        return None, "D3_funding_guard"
    d3 = f"D3 spread {sp} ≤ {ref}×{cfg.spread_mult} · bayatlık yok · funding guard geçti"
    sl, tp = cfg.sl_pct.get(state), cfg.tp_pct.get(state)
    if sl is None or tp is None:
        return None, "sl_tp_yok"   # ölçülmemiş eşikle pozisyon açılmaz
    price = v["best_ask"] if cell.dir == "long" else v["best_bid"]
    cid = f"e{sym}{v['bar_end_ms']}{'L' if cell.dir == 'long' else 'S'}"
    return EntryIntent(symbol=sym, side=cell.dir, notional=cfg.notional_usdt, price=price, horizon_min=cell.h,
                       sl_pct=sl, tp_pct=tp, entry_state=state, cell=cell.key(), client_order_id=cid[:36],
                       explain=" · ".join((d1, d2, d3)), report_hash=cfg.report_hash), None
