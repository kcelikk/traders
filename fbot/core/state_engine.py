"""Market State Engine (Faz 6) — araştırma kurallarının çekirdek karşılığı. Saf.

Faz 3'teki `fbot/research/features.py` ve `states.py` fonksiyonları **değiştirilmeden** kullanılır;
bu modül yalnızca sembol başına kayan pencere tutar ve geçişleri komuta çevirir (docs/design/faz6-giris-mantigi.md §2).
Bit-eşitlik testi: tests/test_state_engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from fbot.core.commands import StateChanged
from fbot.research.features import FeatureConfig, compute_features
from fbot.research.states import StateConfig, label_state


@dataclass(frozen=True)
class StateEngineConfig:
    W: int
    N_short: int
    N_long: int
    p_lo: float
    p_hi: float

    @property
    def feature_config(self) -> FeatureConfig:
        return FeatureConfig(W=self.W, N_short=self.N_short, N_long=self.N_long)

    @property
    def state_config(self) -> StateConfig:
        return StateConfig(p_lo=self.p_lo, p_hi=self.p_hi)


class SymbolStateEngine:
    """Sembol başına bar penceresi + etiketleme. Pencere `W + N_long + 2` bardan kısa tutulmaz."""

    def __init__(self, symbol: str, cfg: StateEngineConfig):
        self.symbol = symbol
        self.cfg = cfg
        self.fcfg = cfg.feature_config
        self.scfg = cfg.state_config
        self.bars: list[dict] = []
        self.label = "S0"
        self.features: dict = {}
        self.since_bar_ms: int | None = None
        self.bars_in_state = 0

    def _keep(self) -> int:
        """Persentilin persentili: vol_ratio W bar ister, onun persentili W bar daha → 2W (+ pencere payı).
        Kısa tutulursa pct_vol_ratio/pct_spread sessizce None kalır ve S3/S4 hiç etiketlenmez."""
        return 2 * self.cfg.W + self.cfg.N_long + 2

    def on_bar(self, bar: dict) -> tuple[str, dict]:
        """Bar ekler; (etiket, feature'lar) döndürür. Araştırma kodunun aynısını çağırır."""
        self.bars.append(bar)
        if len(self.bars) > self._keep():
            del self.bars[:-self._keep()]
        self.features = compute_features(self.bars, self.fcfg)[-1]
        self.label = label_state(self.features, self.scfg)
        return self.label, self.features

    def on_bar_cmds(self, bar: dict) -> tuple[str, dict, list]:
        """on_bar + geçiş komutu (yalnızca etiket değiştiğinde)."""
        prev = self.label
        label, feats = self.on_bar(bar)
        if label == prev:
            self.bars_in_state += 1
            return label, feats, []
        self.bars_in_state = 0
        self.since_bar_ms = bar["end_ms"]
        return label, feats, [StateChanged(symbol=self.symbol, from_state=prev, to_state=label, bar_end_ms=bar["end_ms"],
                                           confidence=confidence(feats, label, self.scfg), evidence=evidence(feats), counter=counter(feats))]


def _fmt(f: dict, key: str) -> str:
    v = f.get(key)
    return f"{key}=" + ("None" if v is None else f"{v:.2f}")


def evidence(f: dict) -> str:
    return " ".join(_fmt(f, k) for k in ("pct_ret_long", "pct_rv_long", "pct_rv_short", "pct_vol_ratio"))


def counter(f: dict) -> str:
    """Koşulu bozmaya en yakın feature (karşıt kanıt, prompt 5.5)."""
    return " ".join(_fmt(f, k) for k in ("pct_spread",)) + (f" imb_short={f['imb_short']:.2f}" if f.get("imb_short") is not None else " imb_short=None")


def confidence(f: dict, state: str, cfg: StateConfig) -> float | None:
    """Koşulların eşiğe uzaklığının minimumu. Skor değildir; karara girmez (yalnızca raporlama)."""
    lo, hi = cfg.p_lo, cfg.p_hi
    pr, prl, prs, pvr = f.get("pct_ret_long"), f.get("pct_rv_long"), f.get("pct_rv_short"), f.get("pct_vol_ratio")
    if state == "S1" and None not in (pr, prl):
        return round(min(pr - hi, prl - lo, hi - prl), 4)
    if state == "S2" and None not in (pr, prl):
        return round(min(lo - pr, prl - lo, hi - prl), 4)
    if state == "S3" and prl is not None:
        return round(lo - prl, 4)
    if state == "S4" and None not in (prs, pvr):
        return round(min(prs - hi, pvr - hi), 4)
    return None
