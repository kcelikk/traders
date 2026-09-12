"""Strateji kayıt defteri: kimlik, kod parmak izi ve mod zorlaması. Saf.

`code_hash` dışarıdan verilir (dosya okuma I/O kenarında, `fbot/identity.py`). Kayıt onu yalnız
taşır ve her karara damgalar: hangi kararın hangi kodla üretildiği sonradan sorulabilmeli.

Registry **sırası sabittir**: eklenme sırası korunur ve niyetler `(strategy_id, symbol)` ile
sıralanır. Aynı kayıt aynı olay dizisinde aynı çıktıyı verir (Rule Zero).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fbot.strategy.manifest import StrategyManifest


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Registered:
    manifest: StrategyManifest
    strategy: object
    code_hash: str

    @property
    def id(self) -> str:
        return self.manifest.id


@dataclass
class StrategyRegistry:
    mode: str = "replay"
    items: dict = field(default_factory=dict)       # id → Registered (ekleme sırası korunur)
    blocked: dict = field(default_factory=dict)     # id → neden (mod/terfi engeli)

    def register(self, manifest: StrategyManifest, strategy, code_hash: str) -> Registered:
        if manifest.id in self.items or manifest.id in self.blocked:
            raise RegistryError(f"strateji kimliği zaten kayıtlı: {manifest.id}")
        if getattr(strategy, "id", manifest.id) != manifest.id:
            raise RegistryError(f"manifest kimliği {manifest.id} ile kod kimliği {strategy.id} uyuşmuyor")
        if getattr(strategy, "version", manifest.version) != manifest.version:
            raise RegistryError(f"{manifest.id}: manifest sürümü {manifest.version}, kod sürümü {strategy.version}")
        why = manifest.may_run(self.mode)
        reg = Registered(manifest=manifest, strategy=strategy, code_hash=code_hash)
        if why is not None:
            self.blocked[manifest.id] = why         # sessizce atlanmaz: neden kayda geçer
            return reg
        self.items[manifest.id] = reg
        return reg

    def active(self) -> list:
        return [self.items[i] for i in self.items]

    def get(self, strategy_id: str) -> Registered | None:
        return self.items.get(strategy_id)

    def view(self) -> dict:
        return {"mode": self.mode,
                "active": [{"id": r.manifest.id, "version": r.manifest.version,
                            "code_hash": r.code_hash, "promotion": r.manifest.promotion_state}
                           for r in self.active()],
                "blocked": dict(sorted(self.blocked.items()))}
