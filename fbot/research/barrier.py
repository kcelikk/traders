"""SL/TP bariyer değerlendirmesi (üçlü bariyer: stop, hedef, süre). Saf; I/O yok.

Bir girişin sonucu, ileri barların yüksek/düşük değerleriyle belirlenir:
  · long: `low <= sl` → stop, `high >= tp` → hedef
  · short: aynası
  · `max_hold` bar içinde hiçbiri olmazsa son barın kapanışından çıkılır

**Bilinen sınır:** 1 dk barı içinde iki bariyere de dokunulmuşsa sıra bilinemez. Stop önce varsayılır.
Bu varsayım sonucu karamsar yönde yanlı yapar; kâr lehine yanlılık üretmez (ADR 0008 ruhu).

Maliyet her sonuçtan düşülür; maliyetsiz sonuç raporlanmaz. Uzun tutmalarda **funding** ihmal
edilemez: 8 saatte bir ödenir, 30 saatlik bir pozisyon üç ödeme görür. Funding, `next_funding_ms`
alanının değiştiği barlarda o barın `funding_rate` değeriyle işlenir; long pozitif oranda öder,
short alır.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BarrierConfig:
    sl_pct: float          # giriş fiyatından uzaklık, yüzde
    tp_pct: float
    max_hold: int          # bar
    cost_pct: float        # gidiş-dönüş işlem maliyeti (komisyon + spread), yüzde
    funding: bool = False  # tutma süresi boyunca geçilen funding ödemeleri ayrıca hesaplanır


def evaluate(entry: float, side: str, future: list[dict], cfg: BarrierConfig) -> dict | None:
    """Tek bir girişin sonucu. İleri bar yoksa `None` (look-ahead yerine eksik veri)."""
    if not future or entry <= 0:
        return None
    long = side == "long"
    sl = entry * (1 - cfg.sl_pct / 100) if long else entry * (1 + cfg.sl_pct / 100)
    tp = entry * (1 + cfg.tp_pct / 100) if long else entry * (1 - cfg.tp_pct / 100)
    fund, prev_settle = 0.0, future[0].get("next_funding_ms") if cfg.funding else None
    for i, b in enumerate(future[: cfg.max_hold], start=1):
        hit_sl = b["low"] <= sl if long else b["high"] >= sl
        hit_tp = b["high"] >= tp if long else b["low"] <= tp
        if hit_sl:                       # aynı barda ikisi de varsa stop önce (kötümser)
            return _out("sl", entry, sl, long, i, cfg, fund)
        if hit_tp:
            return _out("tp", entry, tp, long, i, cfg, fund)
        if cfg.funding:
            nf, rate = b.get("next_funding_ms"), b.get("funding_rate")
            if nf is not None and prev_settle is not None and nf != prev_settle and rate is not None:
                fund += float(rate) * 100 * (1 if long else -1)     # long pozitif oranda öder
            prev_settle = nf if nf is not None else prev_settle
    n = min(cfg.max_hold, len(future))
    return _out("timeout", entry, future[n - 1]["close"], long, n, cfg, fund)


def _out(reason: str, entry: float, exit_px: float, long: bool, bars: int, cfg: BarrierConfig, fund: float = 0.0) -> dict:
    gross = (exit_px / entry - 1) * 100 * (1 if long else -1)
    return {"reason": reason, "bars": bars, "exit": exit_px, "funding_pct": fund,
            "gross_pct": gross, "net_pct": gross - cfg.cost_pct - fund}
