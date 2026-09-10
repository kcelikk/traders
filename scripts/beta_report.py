"""BTC-beta dağılımı (Faz 5 K9 tavanı için ölçüm). Girdi: data/research/<run>/bars.jsonl
Kullanım: python -m scripts.beta_report data/research/hist-30d/bars.jsonl [--window 240]"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from fbot.research.beta import beta_series
from scripts.latency_core import percentiles

NOTIONAL = 80


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("bars")
    ap.add_argument("--window", type=int, default=240)
    ap.add_argument("--ref", default="BTCUSDT")
    a = ap.parse_args(argv)
    by = defaultdict(list)
    for line in Path(a.bars).read_text().splitlines():
        if line.strip():
            b = json.loads(line)
            by[b["symbol"]].append(b)
    for v in by.values():
        v.sort(key=lambda x: x["start_ms"])
    ref = by.get(a.ref)
    if not ref:
        print(f"{a.ref} yok"); return
    print(f"# BTC-beta dağılımı — `{Path(a.bars).parent.name}` (pencere {a.window} bar, referans {a.ref})\n")
    print(f"Kapsam: {len(ref)} bar · {len(by)} sembol. beta = Cov(r_alt, r_btc) / Var(r_btc), 1 dk log getiri.\n")
    print("| Sembol | n | beta p05 | p50 | p95 | maks | 80 USDT'nin BTC karşılığı (p50) |")
    print("|---|---|---|---|---|---|---|")
    rows = {}
    for sym in sorted(by):
        s = beta_series(ref, by[sym], window=a.window)
        if not s:
            continue
        bs = [x["beta"] for x in s]
        p = percentiles(bs, (5, 50, 95))
        rows[sym] = p
        print(f"| {sym} | {len(bs)} | {p['p5']:.2f} | {p['p50']:.2f} | {p['p95']:.2f} | {max(bs):.2f} | {NOTIONAL * p['p50']:.0f} USDT |")
    if rows:
        worst = sum(max(abs(p["p95"]), abs(p["p5"])) for p in rows.values()) / len(rows)
        top5 = sorted((max(abs(p["p95"]), abs(p["p5"])) for p in rows.values()), reverse=True)[:5]
        print(f"\n## Tavan için ölçüm\n")
        print(f"- Sembol başına ortalama |beta| (p95/p05 kötü tarafı): **{worst:.2f}**")
        print(f"- En yüksek 5 sembolün |beta|'sı: {', '.join(f'{x:.2f}' for x in top5)}")
        print(f"- 5 eşzamanlı pozisyon × 80 USDT = 400 USDT brüt. Hepsi aynı yönde ve en yüksek beta'lı 5 sembolde olsaydı:")
        print(f"  net BTC-beta maruziyeti ≈ **{NOTIONAL * sum(top5):.0f} USDT** (brüt 400 USDT'nin {NOTIONAL * sum(top5) / 400:.2f} katı)")
        print(f"- Ortalama durumda (rastgele 5 sembol, aynı yön): ≈ {NOTIONAL * 5 * worst:.0f} USDT")
        print(f"\nKarar önerisi: `beta_cap_usdt` brüt tavana (400) yakın seçilirse aynı yönde 5 pozisyon fiilen engellenir;")
        print(f"gevşek seçilirse K9 hiç devreye girmez. Ölçüme göre orta nokta ≈ {round(NOTIONAL * 5 * worst / 50) * 50:.0f} USDT.")
        print(f"\n**Kârlılık gösterilmedi (ADR 0010).** Bu tablo yalnızca maruziyet ölçümüdür.")


if __name__ == "__main__":
    main(sys.argv[1:])
