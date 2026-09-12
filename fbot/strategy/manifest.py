"""Strateji manifest'i: `strategies/<id>/manifest.toml` içeriğinin **saf** çözümlemesi.

Dosya okuma burada değildir (saflık): çağıran TOML'u sözlüğe çevirip verir. Böylece manifest
doğrulaması replay'de de aynı şekilde çalışır ve test için dosya gerekmez.

`allowed_modes` ve `promotion_state` birlikte çalışır: terfi etmemiş strateji canlıda ARM olamaz.
Terfi zinciri `draft → replay_ok → paper_ok → testnet_ok → live`; her adım ayrı kanıt ister.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fbot.strategy.base import MODES, PROMOTION

# Hangi terfi durumu hangi modda koşmaya izin verir. Live, ayrı ve en üst adımdır.
MODE_REQUIREMENT = {"replay": "draft", "paper": "replay_ok", "testnet": "paper_ok", "live": "testnet_ok"}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class StrategyManifest:
    id: str
    version: str
    params: dict = field(default_factory=dict)
    symbol_universe: tuple = ()
    required_streams: tuple = ()
    risk_budget: dict = field(default_factory=dict)     # strateji bütçesi: global limitleri aşamaz
    allowed_modes: tuple = ()
    promotion_state: str = "draft"

    def key(self) -> str:
        return f"{self.id}@{self.version}"

    def may_run(self, mode: str) -> str | None:
        """Çalışabilir mi; değilse **neden** değil. Sessiz `False` hata ayıklanamaz."""
        if mode not in MODES:
            return f"bilinmeyen mod: {mode}"
        if mode not in self.allowed_modes:
            return f"{self.key()} bu modda çalışmaya yetkili değil: allowed_modes={list(self.allowed_modes)}"
        need = MODE_REQUIREMENT[mode]
        if PROMOTION.index(self.promotion_state) < PROMOTION.index(need):
            return f"{self.key()} terfi durumu '{self.promotion_state}', {mode} için '{need}' gerekir"
        return None


def parse_manifest(d: dict) -> StrategyManifest:
    for req in ("id", "version"):
        if not d.get(req):
            raise ManifestError(f"manifest '{req}' alanı zorunlu")
    promotion = str(d.get("promotion_state", "draft"))
    if promotion not in PROMOTION:
        raise ManifestError(f"promotion_state {PROMOTION} içinde olmalı: {promotion!r}")
    modes = tuple(d.get("allowed_modes", ()))
    for m in modes:
        if m not in MODES:
            raise ManifestError(f"allowed_modes bilinmeyen mod içeriyor: {m!r}")
    if "live" in modes and promotion != "live":
        # Fail-closed: canlı izni, terfi zincirinin tamamlanmasından **sonra** verilir.
        raise ManifestError("allowed_modes 'live' içeriyor ama promotion_state 'live' değil")
    return StrategyManifest(id=str(d["id"]), version=str(d["version"]),
                            params=dict(d.get("params", {})),
                            symbol_universe=tuple(d.get("symbol_universe", ())),
                            required_streams=tuple(d.get("required_streams", ())),
                            risk_budget=dict(d.get("risk_budget", {})),
                            allowed_modes=modes, promotion_state=promotion)
