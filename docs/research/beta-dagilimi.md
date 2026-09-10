# BTC-beta dağılımı — `hist-30d` (pencere 240 bar, referans BTCUSDT)

Kapsam: 46079 bar · 10 sembol. beta = Cov(r_alt, r_btc) / Var(r_btc), 1 dk log getiri.

| Sembol | n | beta p05 | p50 | p95 | maks | 80 USDT'nin BTC karşılığı (p50) |
|---|---|---|---|---|---|---|
| BNBUSDT | 46049 | 0.40 | 0.69 | 1.17 | 2.02 | 55 USDT |
| BTCUSDT | 46049 | 1.00 | 1.00 | 1.00 | 1.00 | 80 USDT |
| DOGEUSDT | 46049 | 0.67 | 1.24 | 2.39 | 5.82 | 99 USDT |
| ETHUSDT | 46049 | 0.79 | 1.07 | 1.42 | 2.95 | 86 USDT |
| HYPEUSDT | 46049 | 0.68 | 1.12 | 1.90 | 4.13 | 89 USDT |
| IOSTUSDT | 45174 | -0.03 | 0.74 | 1.70 | 5.21 | 59 USDT |
| NEARUSDT | 46049 | 0.66 | 1.44 | 2.67 | 6.28 | 115 USDT |
| SOLUSDT | 46049 | 0.80 | 1.25 | 1.86 | 3.71 | 100 USDT |
| XRPUSDT | 46049 | 0.69 | 1.33 | 2.15 | 4.60 | 106 USDT |
| ZECUSDT | 46049 | 0.84 | 1.58 | 2.86 | 6.04 | 126 USDT |

## Tavan için ölçüm

- Sembol başına ortalama |beta| (p95/p05 kötü tarafı): **1.91**
- En yüksek 5 sembolün |beta|'sı: 2.86, 2.67, 2.39, 2.15, 1.90
- 5 eşzamanlı pozisyon × 80 USDT = 400 USDT brüt. Hepsi aynı yönde ve en yüksek beta'lı 5 sembolde olsaydı:
  net BTC-beta maruziyeti ≈ **958 USDT** (brüt 400 USDT'nin 2.39 katı)
- Ortalama durumda (rastgele 5 sembol, aynı yön): ≈ 765 USDT

Karar önerisi: `beta_cap_usdt` brüt tavana (400) yakın seçilirse aynı yönde 5 pozisyon fiilen engellenir;
gevşek seçilirse K9 hiç devreye girmez. Ölçüme göre orta nokta ≈ 750 USDT.

**Kârlılık gösterilmedi (ADR 0010).** Bu tablo yalnızca maruziyet ölçümüdür.
