"""Maliyet senaryoları. Saf; I/O yok.

Bileşenler ve neden ayrı tutulduğu:

  · **Komisyon** giriş ve çıkış için ayrı. BNB ile ödemede ×0,9 indirim yalnızca komisyona uygulanır.
  · **Spread** geçiş sayısıyla ölçeklenir. Taker emir karşı tarafa geçer ve mid'e göre **yarım
    spread** öder; gidiş-dönüş taker bir tam spread eder. Maker emir geçmez, spread ödemez.
    (Eski model gidiş-dönüşe iki tam spread yazıyordu; karamsar yönde yanlıydı.)
  · **Çıkış türü** maliyeti değiştirir: koruma emri (stop) piyasa emridir, senaryo ne derse desin
    taker ücreti öder. Hedef emri limit olarak beklediğinde maker olabilir.

**Bilinen sınır:** maker giriş post-only emirle yapılır ve **hiç dolmayabilir**. Bariyer testi
girişin her zaman gerçekleştiğini varsayar, bu yüzden maker senaryoları dolum olasılığı bakımından
iyimserdir. Kuyruk pozisyonu da modellenmez (ADR 0013). Maker sonuçları üst sınır olarak okunmalıdır.
"""
from __future__ import annotations

from dataclasses import dataclass

BNB = 0.9
TAKER_EXITS = ("sl", "timeout")     # stop ve süre dolumu her zaman piyasa emri


@dataclass(frozen=True)
class CostScenario:
    name: str
    fee_in_pct: float
    fee_out_pct: float
    spread_crossings: float = 2.0      # taker/taker = 2 (her yönde yarım spread), maker/taker = 1, maker/maker = 0
    bnb_discount: bool = False
    taker_fee_pct: float | None = None  # koruma emrinin ücreti; None ise fee_out kullanılır

    def _fees(self, fee_out: float) -> float:
        f = self.fee_in_pct + fee_out
        return f * BNB if self.bnb_discount else f

    def _spread(self, spread_bps: float, crossings: float) -> float:
        return crossings * (spread_bps / 100.0) / 2.0      # bir geçiş = yarım spread

    def entry_exit_pct(self, spread_bps: float) -> float:
        """Senaryonun nominal gidiş-dönüş maliyeti (çıkış türünden bağımsız)."""
        return self._fees(self.fee_out_pct) + self._spread(spread_bps, self.spread_crossings)

    def cost_for(self, reason: str, spread_bps: float) -> float:
        """Çıkış türüne göre maliyet. Stop ve süre dolumu taker; hedef senaryonun dediği gibi."""
        if reason not in TAKER_EXITS or self.taker_fee_pct is None:
            return self.entry_exit_pct(spread_bps)
        # çıkış zorunlu taker: komisyon taker olur, çıkış geçişi de bir yarım spread ekler
        crossings = max(self.spread_crossings, 1.0) if self.spread_crossings < 1.0 else self.spread_crossings
        return self._fees(self.taker_fee_pct) + self._spread(spread_bps, crossings)


def scenarios_from_config(cfg: dict) -> list[CostScenario]:
    out = []
    for s in (cfg.get("costs") or {}).get("scenarios") or []:
        out.append(CostScenario(name=s["name"], fee_in_pct=float(s["fee_in_pct"]), fee_out_pct=float(s["fee_out_pct"]),
                                spread_crossings=float(s.get("spread_crossings", 2.0)),
                                bnb_discount=bool(s.get("bnb_discount", False)),
                                taker_fee_pct=float(s["taker_fee_pct"]) if s.get("taker_fee_pct") is not None else None))
    return out


def pick(scenarios: list[CostScenario], name: str) -> CostScenario:
    for s in scenarios:
        if s.name == name:
            return s
    raise KeyError(f"bilinmeyen maliyet senaryosu: {name} (geçerli: {', '.join(s.name for s in scenarios)})")
