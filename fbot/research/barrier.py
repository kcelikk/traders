"""SL/TP bariyer değerlendirmesi (üçlü bariyer: stop, hedef, süre). Saf; I/O yok.

Bir girişin sonucu, ileri barların yüksek/düşük değerleriyle belirlenir:
  · long: `low <= sl` → stop, `high >= tp` → hedef
  · short: aynası
  · `max_hold` bar içinde hiçbiri olmazsa son barın kapanışından çıkılır

**Bilinen sınır:** 1 dk barı içinde iki bariyere de dokunulmuşsa sıra bilinemez. Stop önce varsayılır.
Bu varsayım sonucu karamsar yönde yanlı yapar; kâr lehine yanlılık üretmez (ADR 0008 ruhu).
Maliyet her sonuçtan düşülür; maliyetsiz sonuç raporlanmaz.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BarrierConfig:
    sl_pct: float          # giriş fiyatından uzaklık, yüzde
    tp_pct: float
    max_hold: int          # bar
    cost_pct: float        # gidiş-dönüş toplam maliyet (komisyon + spread + funding), yüzde


def evaluate(entry: float, side: str, future: list[dict], cfg: BarrierConfig) -> dict | None:
    """Tek bir girişin sonucu. İleri bar yoksa `None` (look-ahead yerine eksik veri)."""
    if not future or entry <= 0:
        return None
    long = side == "long"
    sl = entry * (1 - cfg.sl_pct / 100) if long else entry * (1 + cfg.sl_pct / 100)
    tp = entry * (1 + cfg.tp_pct / 100) if long else entry * (1 - cfg.tp_pct / 100)
    for i, b in enumerate(future[: cfg.max_hold], start=1):
        hit_sl = b["low"] <= sl if long else b["high"] >= sl
        hit_tp = b["high"] >= tp if long else b["low"] <= tp
        if hit_sl:                       # aynı barda ikisi de varsa stop önce (kötümser)
            return _out("sl", entry, sl, long, i, cfg)
        if hit_tp:
            return _out("tp", entry, tp, long, i, cfg)
    b = future[min(cfg.max_hold, len(future)) - 1]
    return _out("timeout", entry, b["close"], long, min(cfg.max_hold, len(future)), cfg)


def _out(reason: str, entry: float, exit_px: float, long: bool, bars: int, cfg: BarrierConfig) -> dict:
    gross = (exit_px / entry - 1) * 100 * (1 if long else -1)
    return {"reason": reason, "bars": bars, "exit": exit_px,
            "gross_pct": gross, "net_pct": gross - cfg.cost_pct}
