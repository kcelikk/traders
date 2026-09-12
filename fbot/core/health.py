"""Sağlık modeli: ortogonal gerçekler ve onlardan türeyen izinler. Saf.

Bugünkü davranış tek bir bayrağa dayanıyor: herhangi bir kategori bayatsa **bütün** açık pozisyonlar
`FROZEN` oluyor ve `_tick_positions` onları atlıyor. Yani bayatlık, korumasız bir pozisyonu kurtaracak
kuralı da (koruma zaman aşımı → acil çıkış) susturuyor. Bayat fiyat, "hiçbir şey yapma" demek değildir;
"fiyata dayanan kurallara güvenme" demektir.

Gerçekler ortogonaldir; karar onlardan **türetilir**:

    market_age[symbol]   · user_stream_age · reconciled · kill_switch · warmup

    entry_allowed        — yeni pozisyon açılabilir mi
    exit_mode            — FULL | PROTECTION_ONLY | HALTED

`FULL`: bütün çıkış kuralları çalışır.
`PROTECTION_ONLY`: yalnız **borsa tarafı koruma eksikliğini** gideren kural çalışır (koruma zaman
aşımı → acil çıkış). Fiyata dayanan kurallar (yedek stop, kâr kilidi, kısmi azaltma, durum bozulması)
bekler; pozisyonun borsadaki `closePosition` emri zaten devrededir.
`HALTED`: hiçbir kural emir üretmez. Mutabakat yoksa iç durumun borsayla aynı olduğunu bilmiyoruz;
hayalet bir pozisyona çıkış emri göndermek gerçek bir pozisyonu ters çevirebilir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FULL, PROTECTION_ONLY, HALTED = "FULL", "PROTECTION_ONLY", "HALTED"


@dataclass(frozen=True)
class HealthFacts:
    """Ölçülen gerçekler. Hiçbiri diğerinden türetilmez; hepsi ayrı ayrı raporlanır."""
    stale: dict = field(default_factory=dict)        # kategori → bayat mı
    reconciled: bool = True
    kill_switch: bool = False
    warmup_done: bool = True
    user_stream_age_s: float | None = None           # None: akış yok ya da hiç çerçeve gelmedi
    user_stream_limit_s: float | None = None

    @property
    def market_stale(self) -> bool:
        return any(self.stale.values())

    @property
    def user_stream_stale(self) -> bool:
        if self.user_stream_age_s is None or self.user_stream_limit_s is None:
            return False                              # bilinmiyor ≠ bayat
        return self.user_stream_age_s > self.user_stream_limit_s


def exit_mode(f: HealthFacts) -> str:
    if not f.reconciled:
        return HALTED
    if f.market_stale:
        return PROTECTION_ONLY
    return FULL


def entry_allowed(f: HealthFacts) -> bool:
    """Girişin kendi kapıları risk motorunda (K1–K18); burada yalnız sağlık tarafı."""
    return f.reconciled and not f.kill_switch and not f.market_stale and f.warmup_done


def view(f: HealthFacts) -> dict:
    """Konsol ve kayıt için tek sözlük: gerçekler ve türetilenler birlikte, hangisi hangisi belli."""
    return {"facts": {"market_stale": f.market_stale, "stale": dict(sorted(f.stale.items())),
                      "reconciled": f.reconciled, "kill_switch": f.kill_switch,
                      "warmup_done": f.warmup_done, "user_stream_age_s": f.user_stream_age_s,
                      "user_stream_stale": f.user_stream_stale},
            "derived": {"exit_mode": exit_mode(f), "entry_allowed": entry_allowed(f)}}
