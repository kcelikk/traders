"""Devre kesici: günlük net zarar, ardışık zarar ve arıza dedektörü. Saf.

Üç ayrı şey, karıştırılmaz:

1. **Arıza dedektörü** (`RunawayDetector`, `risk.py`): pencerede anormal emir/ret sayısı. Yazılım
   hatasını yakalar, piyasa sonucunu değil. Bugüne kadar hiçbir yerde **instantiate edilmiyordu**.
2. **Günlük net zarar limiti**: piyasa sonucu. Aşımda **yeni giriş durur**, açık pozisyonlar mevcut
   politikayla yönetilmeye devam eder (kapatma zorlanmaz: panik satışı politikası değil).
3. **Kalıcı kill switch**: elle sıfırlanan son katman. 418 (ban) ve arıza dedektörü buna bağlanır.

`mode = "alarm"` ile başlar: bir hafta yanlış-pozitif sayılır, sonra `"enforce"`. Alarm modunda
karar **değişmez**, yalnız olay üretilir — ölçmeden kısıtlama koymayız (CLAUDE.md).

Günlük pencere: gerçekleşen PnL kalemlerinin **borsa zaman damgasına** göre UTC günü. İç saat
kullanılmaz (Rule Zero: iş mantığı sistem saatini okumaz).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ALARM, ENFORCE = "alarm", "enforce"
DAY_MS = 86_400_000


@dataclass(frozen=True)
class BreakerConfig:
    mode: str = ALARM                              # alarm | enforce
    daily_net_loss_usdt: Decimal | None = None     # gün içi kümülatif net zarar eşiği (pozitif sayı)
    consecutive_loss_limit: int | None = None      # ardışık zararlı işlem sayısı
    kill_on_runaway: bool = True                   # arıza dedektörü kill switch tetikler


@dataclass
class BreakerState:
    day_ms: int | None = None                      # açık UTC günü (ms cinsinden gün başlangıcı)
    day_net_usdt: Decimal = Decimal(0)
    consecutive_losses: int = 0
    tripped: list = field(default_factory=list)    # bu gün tetiklenen kurallar (tekrar olay üretmemek için)

    def day_of(self, t_ms: int) -> int:
        return (t_ms // DAY_MS) * DAY_MS


def on_trade(cfg: BreakerConfig, st: BreakerState, net_usdt: Decimal, t_ms: int) -> list:
    """Kapanan işlemi işler ve tetiklenen kuralları döndürür. Gün değişince sayaçlar sıfırlanır."""
    day = st.day_of(t_ms)
    if st.day_ms != day:
        st.day_ms, st.day_net_usdt, st.tripped = day, Decimal(0), []
        st.consecutive_losses = 0
    st.day_net_usdt += net_usdt
    st.consecutive_losses = st.consecutive_losses + 1 if net_usdt < 0 else 0
    out = []
    if (cfg.daily_net_loss_usdt is not None and st.day_net_usdt <= -cfg.daily_net_loss_usdt
            and "daily_net_loss" not in st.tripped):
        st.tripped.append("daily_net_loss")
        out.append({"rule": "daily_net_loss", "day_net_usdt": str(st.day_net_usdt),
                    "limit_usdt": str(cfg.daily_net_loss_usdt), "mode": cfg.mode})
    if (cfg.consecutive_loss_limit is not None and st.consecutive_losses >= cfg.consecutive_loss_limit
            and "consecutive_loss" not in st.tripped):
        st.tripped.append("consecutive_loss")
        out.append({"rule": "consecutive_loss", "count": st.consecutive_losses,
                    "limit": cfg.consecutive_loss_limit, "mode": cfg.mode})
    return out


def entry_blocked(cfg: BreakerConfig, st: BreakerState) -> str | None:
    """`enforce` modunda tetiklenmiş kural varsa yeni giriş durur. Alarm modunda karar değişmez."""
    if cfg.mode != ENFORCE or not st.tripped:
        return None
    return ",".join(st.tripped)
