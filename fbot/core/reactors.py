"""Reaktörler: olay-tetiklemeli çıkış değerlendirmesi. **Saf**, determinizm garantileri içeride.

Bugün çıkış kuralları yalnız saniyede bir `ctrl/tick` olayında değerlendiriliyor; yani fiyat
hareketiyle çıkış kararı arasında **1 saniyeye kadar** kuantizasyon var. Reaktör, aynı kuralları
`bookTicker` / `markPriceUpdate` olaylarında da değerlendirir.

Determinizm garantileri (ADR 0007):
  · reaktör saat okumaz, `now_ns` parametre gelir,
  · kayıt defteri sabit sırada, üretilen niyetler `(reactor_id, pos_id)` ile sıralanır,
  · `exit_in_flight` (Gate 3) çift üretimi engeller,
  · shadow niyetler ayrı hash zincirine yazılır (`commands.is_shadow`).

**Fiyat referansı kural başına deklare edilir.** R1 yedek stop `MARK` kullanır çünkü borsadaki
karşılığı `workingType=MARK_PRICE`; dinamik MARKET çıkış değerlendirmesi `BBO` kullanır
(long → best bid). Tek bir "fiyat" kavramı yoktur (CLAUDE.md).

**Coalescing/throttle yoktur.** Önce ölçülür (Gate 4 bütçesi: `bookTicker` dalında +%20).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fbot.core.commands import ShadowIntent

OFF, SHADOW, ACTIVE = "off", "shadow", "active"
MARK, BBO = "MARK", "BBO"


@dataclass(frozen=True)
class ReactorConfig:
    mode: str = OFF                    # off | shadow | active (active ayrı onay kapısı)
    enabled: tuple = ()                # reaktör kimlikleri; sıra sabittir


@dataclass(frozen=True)
class ReactorContext:
    """Reaktörün gördüğü her şey. Saat, ağ, kayıt yok; yalnız veri."""
    pos: object
    symbol: str
    mark: Decimal | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    now_ns: int
    event_kind: str
    pm: object                          # PositionManager: kural eşiklerinin tek kaynağı


class BackupStopReactor:
    """R1 yedek stop: mark, stop seviyesini geçtiyse uygulama tarafı çıkış. Borsadaki
    `STOP_MARKET closePosition` emri ilk savunmadır; bu ikinci katmandır (CLAUDE.md koruma katmanları).

    Referans **MARK**: borsadaki koruma emri de `MARK_PRICE` ile tetikleniyor; BBO kullanmak iki
    katmanı farklı fiyata bakar hâle getirir.
    """

    id = "backup_stop"
    subscribes = ("bookTicker", "markPriceUpdate")
    requires_open_position = True
    reference = MARK

    def evaluate(self, ctx: ReactorContext):
        pos = ctx.pos
        if ctx.mark is None or pos.sl_price is None or getattr(pos.state, "value", pos.state) != "MANAGED":
            return []
        crossed = ctx.mark <= pos.sl_price if pos.side == "long" else ctx.mark >= pos.sl_price
        if not crossed:
            return []
        return [(self.id, pos.pos_id, ctx.symbol, "backup_stop", self.reference, ctx.mark)]


REGISTRY = {r.id: r for r in (BackupStopReactor(),)}    # sabit sıra: dict ekleme sırası korunur


def enabled_reactors(cfg: ReactorConfig):
    """Yalnız config'te açıkça yazılanlar, **yazıldığı sırayla**. Bilinmeyen kimlik sessizce
    atlanmaz: yapılandırma hatası görünür olmalı."""
    out = []
    for rid in cfg.enabled:
        r = REGISTRY.get(rid)
        if r is None:
            raise ValueError(f"bilinmeyen reactor: {rid!r} (bilinenler: {', '.join(REGISTRY)})")
        out.append(r)
    return out


def react(cfg: ReactorConfig, reactors, positions: dict, pos_ids, symbol: str, market, now_ns: int,
          event_kind: str, pm) -> list:
    """Bir sembolde açık pozisyon varken olay-tetiklemeli değerlendirme.

    `pos_ids` çağıranın sembol indeksinden gelir: olay başına tüm pozisyonları taramak kabul
    edilemez (Gate 4 bütçesi).
    """
    if cfg.mode == OFF or not pos_ids:
        return []
    intents = []
    for r in reactors:
        if event_kind not in r.subscribes:
            continue
        for pid in sorted(pos_ids):
            pos = positions.get(pid)
            if pos is None or getattr(pos.state, "value", pos.state) == "CLOSED":
                continue
            if pm is not None and pm.exit_locked(pos, now_ns):
                continue                 # uçuşta çıkış var: ikinci niyet üretilmez (Gate 3)
            ctx = ReactorContext(pos=pos, symbol=symbol, mark=market.mark_price if market else None,
                                 best_bid=market.best_bid if market else None,
                                 best_ask=market.best_ask if market else None,
                                 now_ns=now_ns, event_kind=event_kind, pm=pm)
            intents += r.evaluate(ctx)
    intents.sort(key=lambda i: (i[0], i[1]))
    if cfg.mode == SHADOW:
        return [ShadowIntent(reactor_id=r, pos_id=p, symbol=s, reason=why, reference=ref,
                             price=px, event_ns=now_ns) for r, p, s, why, ref, px in intents]
    # ACTIVE yolu bu gate'te **yok**: yarım implementasyon, hiç implementasyondan tehlikelidir
    # (CLAUDE.md). Shadow gözlemi ve ayrı onay olmadan emir üretilmez.
    raise NotImplementedError("reactors.mode='active' ayrı onay kapısıdır; Gate 4 shadow gözlemi gerekir")
