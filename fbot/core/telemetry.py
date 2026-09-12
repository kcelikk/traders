"""Telemetri: saf, sabit bellekli histogramlar. Hot path'te tahsisat yapmaz.

Neden ayrı modül: ölçüm de bir hot path maliyetidir. `RawEvent`'e alan eklemek her olayda tahsisat
demek; bunun yerine sayaçlar ayrı bir nesnede tutulur ve **kova sayısı sabittir** — liste büyümez,
p99 için sıralama yapılmaz.

Kovalar logaritmik: mikro saniyeden saniyeye kadar tek tabloda. Persentil kova sınırından okunur,
yani **yaklaşık**; rapor bunu gizlemez (`approx: true`).

`Clock` yok: her `observe` çağrısı ölçülen değeri parametre alır (Rule Zero #2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 1 µs'ten 16,7 s'ye: her kova bir öncekinin iki katı. 25 kova sabit bellek.
BUCKETS_NS = tuple(1_000 * (2 ** i) for i in range(25))


@dataclass
class Histogram:
    """Sabit kovalı histogram. `count`, `total` ve kova sayaçları dışında bellek büyümez."""
    name: str
    counts: list = field(default_factory=lambda: [0] * (len(BUCKETS_NS) + 1))
    count: int = 0
    total_ns: int = 0
    max_ns: int = 0

    def observe(self, value_ns: int) -> None:
        self.count += 1
        self.total_ns += value_ns
        if value_ns > self.max_ns:
            self.max_ns = value_ns
        lo, hi = 0, len(BUCKETS_NS)
        while lo < hi:                      # ikili arama: kova sayısı sabit, maliyet log(25)
            mid = (lo + hi) // 2
            if value_ns <= BUCKETS_NS[mid]:
                hi = mid
            else:
                lo = mid + 1
        self.counts[lo] += 1

    def quantile_ns(self, q: float) -> int | None:
        """Kova sınırından okunan **yaklaşık** persentil. Kesin değer istiyorsan ham örnek gerekir."""
        if not self.count:
            return None
        target = q * self.count
        seen = 0
        for i, c in enumerate(self.counts):
            seen += c
            if seen >= target:
                return BUCKETS_NS[i] if i < len(BUCKETS_NS) else self.max_ns
        return self.max_ns

    def view(self) -> dict:
        return {"n": self.count, "approx": True,
                "p50_us": _us(self.quantile_ns(0.5)), "p95_us": _us(self.quantile_ns(0.95)),
                "p99_us": _us(self.quantile_ns(0.99)), "max_us": _us(self.max_ns),
                "avg_us": _us(self.total_ns // self.count) if self.count else None}


def _us(ns: int | None) -> float | None:
    return None if ns is None else round(ns / 1000, 1)


@dataclass
class Telemetry:
    """İsimli histogram kümesi. Sözlük sıralı: rapor çıktısı deterministiktir."""
    hists: dict = field(default_factory=dict)

    def observe(self, name: str, value_ns: int) -> None:
        h = self.hists.get(name)
        if h is None:
            h = self.hists[name] = Histogram(name)
        h.observe(value_ns)

    def view(self) -> dict:
        return {name: self.hists[name].view() for name in sorted(self.hists)}
