# Faz 3 araştırma raporu — `rec-72h`

Kapsam: 4.9 saat, 10 sembol, 2960 bar. Config `a116fadfb098` (W=240, N=5/15, p=0.2/0.8). Keşif/doğrulama ayrımı: 1789039859999 ms epoch (%70). Bootstrap n=2000, seed=20260910.

## Durum dağılımı

| Durum | bar | oran |
|---|---|---|
| S0 | 2924 | 98.8% |
| S1 | 14 | 0.5% |
| S2 | 11 | 0.4% |
| S3 | 11 | 0.4% |
| S4 | 0 | 0.0% |

## Geçiş matrisi (satır → sütun)

| | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| S0 | 2902 | 6 | 4 | 2 | 0 |
| S1 | 7 | 7 | 0 | 0 | 0 |
| S2 | 4 | 0 | 7 | 0 | 0 |
| S3 | 1 | 1 | 0 | 9 | 0 |
| S4 | 0 | 0 | 0 | 0 | 0 |

## Hücreler — maliyet senaryosu **taker/taker** (giriş 0.05% + çıkış 0.05% + spread + funding)

| durum | etiket | yön | ufuk | bölüm | n | brüt % | maliyet % | **net %** | medyan | kazanma | CI alt | CI üst | karar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 | trend | long | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S1 | trend | long | 1 dk | doğrulama | 14 | -0.014 | 0.100 | **-0.114** | -0.192 | 0.07 | -0.409 | 0.356 | keşifte elendi |
| S1 | trend | long | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S1 | trend | long | 5 dk | doğrulama | 6 | -0.191 | 0.100 | **-0.291** | -0.325 | 0.17 | -0.927 | 0.420 | keşifte elendi |
| S1 | trend | long | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S1 | trend | long | 15 dk | doğrulama | 4 | -1.069 | 0.100 | **-1.169** | -1.059 | 0.00 | -1.616 | -0.821 | keşifte elendi |
| S2 | trend | short | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S2 | trend | short | 1 dk | doğrulama | 11 | -0.047 | 0.100 | **-0.147** | -0.117 | 0.00 | -0.215 | -0.084 | keşifte elendi |
| S2 | trend | short | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S2 | trend | short | 5 dk | doğrulama | 4 | 0.223 | 0.100 | **0.123** | 0.201 | 0.75 | -0.097 | 0.286 | keşifte elendi |
| S2 | trend | short | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S2 | trend | short | 15 dk | doğrulama | 2 | 0.103 | 0.100 | **0.003** | 0.003 | 0.50 | -0.247 | 0.253 | keşifte elendi |
| S3 | breakout | long | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | long | 1 dk | doğrulama | 5 | 0.284 | 0.100 | **0.184** | 0.132 | 0.60 | -0.210 | 0.577 | keşifte elendi |
| S3 | breakout | long | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | long | 5 dk | doğrulama | 1 | 1.439 | 0.100 | **1.339** | 1.339 | 1.00 | 1.339 | 1.339 | keşifte elendi |
| S3 | breakout | long | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | long | 15 dk | doğrulama | 1 | 3.737 | 0.100 | **3.637** | 3.637 | 1.00 | 3.637 | 3.637 | keşifte elendi |
| S3 | breakout | short | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | short | 1 dk | doğrulama | 6 | -0.108 | 0.100 | **-0.208** | -0.187 | 0.17 | -0.360 | -0.058 | keşifte elendi |
| S3 | breakout | short | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | short | 5 dk | doğrulama | 2 | -0.064 | 0.100 | **-0.164** | -0.164 | 0.50 | -0.527 | 0.200 | keşifte elendi |
| S3 | breakout | short | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | short | 15 dk | doğrulama | 2 | -0.258 | 0.100 | **-0.358** | -0.358 | 0.50 | -1.215 | 0.499 | keşifte elendi |

## Hücreler — maliyet senaryosu **maker/taker** (giriş 0.02% + çıkış 0.05% + spread + funding)

| durum | etiket | yön | ufuk | bölüm | n | brüt % | maliyet % | **net %** | medyan | kazanma | CI alt | CI üst | karar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 | trend | long | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S1 | trend | long | 1 dk | doğrulama | 14 | -0.014 | 0.070 | **-0.084** | -0.162 | 0.07 | -0.379 | 0.386 | keşifte elendi |
| S1 | trend | long | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S1 | trend | long | 5 dk | doğrulama | 6 | -0.191 | 0.070 | **-0.261** | -0.295 | 0.17 | -0.897 | 0.450 | keşifte elendi |
| S1 | trend | long | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S1 | trend | long | 15 dk | doğrulama | 4 | -1.069 | 0.070 | **-1.139** | -1.029 | 0.00 | -1.586 | -0.791 | keşifte elendi |
| S2 | trend | short | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S2 | trend | short | 1 dk | doğrulama | 11 | -0.047 | 0.070 | **-0.117** | -0.087 | 0.18 | -0.185 | -0.054 | keşifte elendi |
| S2 | trend | short | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S2 | trend | short | 5 dk | doğrulama | 4 | 0.223 | 0.070 | **0.153** | 0.231 | 0.75 | -0.067 | 0.316 | keşifte elendi |
| S2 | trend | short | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S2 | trend | short | 15 dk | doğrulama | 2 | 0.103 | 0.070 | **0.033** | 0.033 | 0.50 | -0.217 | 0.283 | keşifte elendi |
| S3 | breakout | long | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | long | 1 dk | doğrulama | 5 | 0.284 | 0.070 | **0.214** | 0.162 | 0.60 | -0.180 | 0.607 | keşifte elendi |
| S3 | breakout | long | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | long | 5 dk | doğrulama | 1 | 1.439 | 0.070 | **1.369** | 1.369 | 1.00 | 1.369 | 1.369 | keşifte elendi |
| S3 | breakout | long | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | long | 15 dk | doğrulama | 1 | 3.737 | 0.070 | **3.667** | 3.667 | 1.00 | 3.667 | 3.667 | keşifte elendi |
| S3 | breakout | short | 1 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | short | 1 dk | doğrulama | 6 | -0.108 | 0.070 | **-0.178** | -0.157 | 0.33 | -0.330 | -0.028 | keşifte elendi |
| S3 | breakout | short | 5 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | short | 5 dk | doğrulama | 2 | -0.064 | 0.070 | **-0.134** | -0.134 | 0.50 | -0.497 | 0.230 | keşifte elendi |
| S3 | breakout | short | 15 dk | keşif | 0 | — | — | **—** | — | — | — | — | n yetersiz |
| S3 | breakout | short | 15 dk | doğrulama | 2 | -0.258 | 0.070 | **-0.328** | -0.328 | 0.50 | -1.185 | 0.529 | keşifte elendi |

## Sembol × durum

| sembol | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| BNBUSDT | 294 | 2 | 0 | 0 | 0 |
| BTCUSDT | 296 | 0 | 0 | 0 | 0 |
| DOGEUSDT | 295 | 0 | 0 | 1 | 0 |
| ETHUSDT | 296 | 0 | 0 | 0 | 0 |
| HYPEUSDT | 287 | 0 | 9 | 0 | 0 |
| IOSTUSDT | 276 | 8 | 2 | 10 | 0 |
| NEARUSDT | 295 | 1 | 0 | 0 | 0 |
| SOLUSDT | 293 | 3 | 0 | 0 | 0 |
| XRPUSDT | 296 | 0 | 0 | 0 | 0 |
| ZECUSDT | 296 | 0 | 0 | 0 | 0 |

## Karar (ADR 0008 §8/§10)

**Hiçbir hücre doğrulama koşullarını sağlamıyor.** Veri süresi ≥ 3 gün değilse sonuç 'yetersiz veri' olarak okunur; ≥ 3 günde bu DUR kararıdır (proje sahibine sunulur).

> Veri 4.9 saat (< 72). Bu rapor ÖN rapordur; ADR 0008 §11 nihai karar için ≥ 3 gün ister.

Rapor hash: `5ff01d444ba76623`
