"""Sembol kirası (lease): bir sembolde aynı anda tek sahip. Saf.

Yeni bir kavram değil — `pending_entries`'in genelleştirilmiş hâli. Eşleme birebir:

    pending_entries[sym] = deadline     →  leases.acquire(sym, strategy_id, now_ns, ttl_ns)
    pending_entries.pop(sym)            →  leases.bind(sym, pos_id) / leases.release(sym)
    TTL süpürmesi (Gate 2.0)            →  leases.sweep(now_ns)

Neden gerek: birden fazla strateji aynı sembolde giriş üretebilir. K7'nin semantiği **değişmez**,
yalnız "meşgul" sorusunun cevabı sahibi de söyler:

  · başka stratejinin kirasındaysa → REJECT
  · kendi kirasında ama pozisyon açıksa → REJECT
  · boşsa → APPROVE

Serbest bırakma iki koşula bağlıdır: pozisyon CLOSED **ve** koruma temizliği terminal. Kira erken
bırakılırsa ikinci bir giriş, ilkinin koruma emirleri hâlâ borsadayken açılır.

TTL zorunludur: süresiz kira, `pending_entries` sızıntısının (Gate 2.0'da kapatıldı) tekrarıdır.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Lease:
    symbol: str
    strategy_id: str
    acquired_ns: int
    expires_ns: int
    pos_id: str | None = None        # dolum gelince bağlanır; bağlıyken TTL işlemez


@dataclass
class LeaseTable:
    leases: dict = field(default_factory=dict)      # sembol → Lease
    conflicts: int = 0                              # başka sahibin kirasına çarpma sayısı (ölçüm)

    def owner(self, symbol: str) -> str | None:
        lease = self.leases.get(symbol)
        return lease.strategy_id if lease else None

    def acquire(self, symbol: str, strategy_id: str, now_ns: int, ttl_ns: int) -> bool:
        cur = self.leases.get(symbol)
        if cur is not None:
            if cur.strategy_id != strategy_id:
                self.conflicts += 1
            return False                            # sahibi kim olursa olsun ikinci kira verilmez
        self.leases[symbol] = Lease(symbol, strategy_id, now_ns, now_ns + ttl_ns)
        return True

    def bind(self, symbol: str, pos_id: str) -> None:
        """Dolum geldi: kira artık pozisyona bağlı, TTL ile düşmez."""
        lease = self.leases.get(symbol)
        if lease is not None:
            lease.pos_id = pos_id

    def release(self, symbol: str) -> None:
        self.leases.pop(symbol, None)

    def release_position(self, pos_id: str) -> list:
        """Pozisyon kapandı ve koruma temizliği bitti: kira bırakılır."""
        out = [s for s, l in self.leases.items() if l.pos_id == pos_id]
        for s in out:
            del self.leases[s]
        return out

    def sweep(self, now_ns: int) -> list:
        """Süresi dolan **bağlanmamış** kiralar düşer. Pozisyona bağlı kira süreyle düşmez:
        açık pozisyonun sembolünü serbest bırakmak ikinci girişe kapı açar."""
        gone = [s for s, l in sorted(self.leases.items())
                if l.pos_id is None and l.expires_ns <= now_ns]
        for s in gone:
            del self.leases[s]
        return gone

    def symbols(self) -> set:
        return set(self.leases)

    def busy_for(self, symbol: str, strategy_id: str) -> str | None:
        """K7 girdisi: sembol bu strateji için meşgul mü, değilse neden değil."""
        lease = self.leases.get(symbol)
        if lease is None:
            return None
        if lease.strategy_id != strategy_id:
            return f"baska_strateji:{lease.strategy_id}"
        return "pozisyon_acik" if lease.pos_id else "giris_ucusta"
