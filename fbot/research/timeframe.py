"""1 dakikalık barlardan üst zaman dilimi üretimi. Saf; I/O yok, saat okumaz.

Neden türetiyoruz da borsadan ayrı kline akışı almıyoruz: tek sıralama noktası ve bit-eşit replay
(Rule Zero) korunsun diye. Üst zaman dilimi, kaydettiğimiz veriden deterministik olarak çıkar.

Kurallar:
  · Kovalar **epoch'a hizalı**: 5 dakikalık kova 07:00–07:05, ilk barın saatine göre kaymaz.
    Borsa mumlarıyla aynı sınır olması, sonradan karşılaştırma yapılabilsin diye gerekir.
  · **Tamamlanmamış son kova düşürülür.** Henüz kapanmamış mumla sinyal üretmek look-ahead'dir.
  · **Eksik dakikası olan kova düşürülür.** Kayıp bar tahmin edilmez.
  · OHLCV dışındaki alanlar (funding, mark, defter dengesizliği, konumlanma metrikleri) kovanın
    **son** barından taşınır. Kaybolurlarsa üst zaman dilimi maliyetsiz ve verisiz görünür.
"""
from __future__ import annotations

M = 60_000


def aggregate(bars: list[dict], minutes: int) -> list[dict]:
    """1 dk barları `minutes` dakikalık barlara toplar. Girdi zamana göre sıralı olmalıdır."""
    if minutes < 1:
        raise ValueError(f"zaman dilimi en az 1 dakika olmalı: {minutes}")
    if any(bars[i]["start_ms"] >= bars[i + 1]["start_ms"] for i in range(len(bars) - 1)):
        raise ValueError("barlar zamana göre artan sırada olmalı")
    if minutes == 1:
        return list(bars)
    span = minutes * M
    out, cur, key = [], [], None
    for b in bars:
        k = b["start_ms"] // span * span
        if k != key:
            if cur:
                out.append(_fold(cur, key, span, minutes))
            cur, key = [], k
        cur.append(b)
    if cur:
        out.append(_fold(cur, key, span, minutes))
    return [b for b in out if b is not None]


def _fold(group: list[dict], start: int, span: int, minutes: int) -> dict | None:
    if len(group) != minutes:          # eksik dakika ya da yarım kova: tahmin yok, atla
        return None
    spreads = [b["spread_bps"] for b in group if b.get("spread_bps") is not None]
    core = {"symbol", "start_ms", "end_ms", "open", "high", "low", "close", "volume", "buy_volume", "trades", "spread_bps"}
    extra = {k: group[-1][k] for k in group[-1] if k not in core}   # kova sonundaki değer geçerlidir
    return {
        **extra,
        "symbol": group[0]["symbol"], "start_ms": start, "end_ms": start + span,
        "open": group[0]["open"], "close": group[-1]["close"],
        "high": max(b["high"] for b in group), "low": min(b["low"] for b in group),
        "volume": sum(b["volume"] for b in group),
        "buy_volume": sum(b["buy_volume"] for b in group),
        "trades": sum(b["trades"] for b in group),
        "spread_bps": (sum(spreads) / len(spreads)) if spreads else None,
    }


def buckets_needed(window_bars: int, minutes: int) -> int:
    """Pencere uzunluğu **bar cinsindendir**, dakika cinsinden değil: 240 bar her zaman 240 kovadır.
    Zaman dilimi büyüdükçe aynı pencere daha uzun bir geçmişi kapsar; bu kasıtlıdır."""
    return window_bars
