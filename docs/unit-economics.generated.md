## Funding (kaynak: GET /fapi/v1/fundingRate, son 500 kayıt; interval: GET /fapi/v1/fundingInfo)

| Sembol | n | aralık (saat) | ort. imzalı (%/aralık) | ort. mutlak (%/aralık) | p95 mutlak | maks mutlak | ort. mutlak (%/saat) | kapsam |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 500 | 8 | +0.0031 | 0.0049 | 0.0100 | 0.0123 | 0.00061 | 166 gün |
| ETHUSDT | 500 | 8 | +0.0023 | 0.0045 | 0.0100 | 0.0230 | 0.00056 | 166 gün |

## Spread ve slippage (kaynak: GET /fapi/v1/depth limit=100, 3 anlık görüntü, 2 s arayla)

| Sembol | best bid | best ask | spread (bps) | alış 100 USDT (bps) | alış 500 USDT (bps) | alış 1000 USDT (bps) | alış 5000 USDT (bps) | alış 20000 USDT (bps) | satış 100 USDT (bps) | satış 500 USDT (bps) | satış 1000 USDT (bps) | satış 5000 USDT (bps) | satış 20000 USDT (bps) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 77951.60 | 77951.70 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | -0.00 | -0.00 |
| ETHUSDT | 2465.16 | 2465.17 | 0.04 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Başabaş hareket (%) — gidiş-dönüş, notional yüzdesi

Varsayımlar: slippage = 1.000 USDT defter yürüyüşü + yarım spread (market emri best'i geçer); funding = ort. mutlak oran × tutma süresi (aleyhte varsayım).

### BTCUSDT

| Komisyon senaryosu | tutma | komisyon | slippage (giriş+çıkış) | funding | **başabaş hareket %** |
|---|---|---|---|---|---|
| VIP0 (doğrulanmadı) taker/taker | 5 dk | 0.100 | 0.000 | 0.0001 | **0.100** |
| VIP0 (doğrulanmadı) taker/taker | 30 dk | 0.100 | 0.000 | 0.0003 | **0.100** |
| VIP0 (doğrulanmadı) taker/taker | 2 sa | 0.100 | 0.000 | 0.0012 | **0.101** |
| VIP0 (doğrulanmadı) taker/taker | 8 sa | 0.100 | 0.000 | 0.0049 | **0.105** |
| VIP0 (doğrulanmadı) taker/taker | 24 sa | 0.100 | 0.000 | 0.0146 | **0.115** |
| VIP0 (doğrulanmadı) maker/taker | 5 dk | 0.070 | 0.000 | 0.0001 | **0.070** |
| VIP0 (doğrulanmadı) maker/taker | 30 dk | 0.070 | 0.000 | 0.0003 | **0.070** |
| VIP0 (doğrulanmadı) maker/taker | 2 sa | 0.070 | 0.000 | 0.0012 | **0.071** |
| VIP0 (doğrulanmadı) maker/taker | 8 sa | 0.070 | 0.000 | 0.0049 | **0.075** |
| VIP0 (doğrulanmadı) maker/taker | 24 sa | 0.070 | 0.000 | 0.0146 | **0.085** |
| VIP0 (doğrulanmadı) maker/maker | 5 dk | 0.040 | 0.000 | 0.0001 | **0.040** |
| VIP0 (doğrulanmadı) maker/maker | 30 dk | 0.040 | 0.000 | 0.0003 | **0.040** |
| VIP0 (doğrulanmadı) maker/maker | 2 sa | 0.040 | 0.000 | 0.0012 | **0.041** |
| VIP0 (doğrulanmadı) maker/maker | 8 sa | 0.040 | 0.000 | 0.0049 | **0.045** |
| VIP0 (doğrulanmadı) maker/maker | 24 sa | 0.040 | 0.000 | 0.0146 | **0.055** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 5 dk | 0.090 | 0.000 | 0.0001 | **0.090** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 30 dk | 0.090 | 0.000 | 0.0003 | **0.090** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 2 sa | 0.090 | 0.000 | 0.0012 | **0.091** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 8 sa | 0.090 | 0.000 | 0.0049 | **0.095** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 24 sa | 0.090 | 0.000 | 0.0146 | **0.105** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 5 dk | 0.063 | 0.000 | 0.0001 | **0.063** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 30 dk | 0.063 | 0.000 | 0.0003 | **0.063** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 2 sa | 0.063 | 0.000 | 0.0012 | **0.064** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 8 sa | 0.063 | 0.000 | 0.0049 | **0.068** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 24 sa | 0.063 | 0.000 | 0.0146 | **0.078** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 5 dk | 0.036 | 0.000 | 0.0001 | **0.036** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 30 dk | 0.036 | 0.000 | 0.0003 | **0.036** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 2 sa | 0.036 | 0.000 | 0.0012 | **0.037** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 8 sa | 0.036 | 0.000 | 0.0049 | **0.041** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 24 sa | 0.036 | 0.000 | 0.0146 | **0.051** |

### ETHUSDT

| Komisyon senaryosu | tutma | komisyon | slippage (giriş+çıkış) | funding | **başabaş hareket %** |
|---|---|---|---|---|---|
| VIP0 (doğrulanmadı) taker/taker | 5 dk | 0.100 | 0.000 | 0.0000 | **0.100** |
| VIP0 (doğrulanmadı) taker/taker | 30 dk | 0.100 | 0.000 | 0.0003 | **0.101** |
| VIP0 (doğrulanmadı) taker/taker | 2 sa | 0.100 | 0.000 | 0.0011 | **0.102** |
| VIP0 (doğrulanmadı) taker/taker | 8 sa | 0.100 | 0.000 | 0.0045 | **0.105** |
| VIP0 (doğrulanmadı) taker/taker | 24 sa | 0.100 | 0.000 | 0.0134 | **0.114** |
| VIP0 (doğrulanmadı) maker/taker | 5 dk | 0.070 | 0.000 | 0.0000 | **0.070** |
| VIP0 (doğrulanmadı) maker/taker | 30 dk | 0.070 | 0.000 | 0.0003 | **0.071** |
| VIP0 (doğrulanmadı) maker/taker | 2 sa | 0.070 | 0.000 | 0.0011 | **0.072** |
| VIP0 (doğrulanmadı) maker/taker | 8 sa | 0.070 | 0.000 | 0.0045 | **0.075** |
| VIP0 (doğrulanmadı) maker/taker | 24 sa | 0.070 | 0.000 | 0.0134 | **0.084** |
| VIP0 (doğrulanmadı) maker/maker | 5 dk | 0.040 | 0.000 | 0.0000 | **0.040** |
| VIP0 (doğrulanmadı) maker/maker | 30 dk | 0.040 | 0.000 | 0.0003 | **0.041** |
| VIP0 (doğrulanmadı) maker/maker | 2 sa | 0.040 | 0.000 | 0.0011 | **0.042** |
| VIP0 (doğrulanmadı) maker/maker | 8 sa | 0.040 | 0.000 | 0.0045 | **0.045** |
| VIP0 (doğrulanmadı) maker/maker | 24 sa | 0.040 | 0.000 | 0.0134 | **0.054** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 5 dk | 0.090 | 0.000 | 0.0000 | **0.090** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 30 dk | 0.090 | 0.000 | 0.0003 | **0.091** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 2 sa | 0.090 | 0.000 | 0.0011 | **0.092** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 8 sa | 0.090 | 0.000 | 0.0045 | **0.095** |
| VIP0 (doğrulanmadı) taker/taker +BNB | 24 sa | 0.090 | 0.000 | 0.0134 | **0.104** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 5 dk | 0.063 | 0.000 | 0.0000 | **0.063** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 30 dk | 0.063 | 0.000 | 0.0003 | **0.064** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 2 sa | 0.063 | 0.000 | 0.0011 | **0.065** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 8 sa | 0.063 | 0.000 | 0.0045 | **0.068** |
| VIP0 (doğrulanmadı) maker/taker +BNB | 24 sa | 0.063 | 0.000 | 0.0134 | **0.077** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 5 dk | 0.036 | 0.000 | 0.0000 | **0.036** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 30 dk | 0.036 | 0.000 | 0.0003 | **0.037** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 2 sa | 0.036 | 0.000 | 0.0011 | **0.038** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 8 sa | 0.036 | 0.000 | 0.0045 | **0.041** |
| VIP0 (doğrulanmadı) maker/maker +BNB | 24 sa | 0.036 | 0.000 | 0.0134 | **0.050** |

## Başabaş kazanma oranı — BTCUSDT, taker/taker VIP0, 30 dk tutma, 1.000 USDT

Toplam maliyet: **0.100%** notional

| hedef hareket | R:R 1.0 | R:R 1.5 | R:R 2.0 |
|---|---|---|---|
| 0.3% | 66.7% | 60.1% | 55.7% |
| 0.5% | 60.0% | 52.1% | 46.7% |
| 1.0% | 55.0% | 46.0% | 40.0% |
| 2.0% | 52.5% | 43.0% | 36.7% |

Maliyetsiz klasik başabaş (karşılaştırma): R:R 1.0 → 50.0%, R:R 1.5 → 40.0%, R:R 2.0 → 33.3%
