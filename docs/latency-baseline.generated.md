# Ölçüm özeti — `baseline-24h-20260910`

Süre: 0.10 saat (1789025558022 → 1789025931983 ms epoch)
Olaylar: rest_keepalive_connect=1, run_end=4, run_start=4, ws_api_connect=1, ws_market_connect=1, ws_public_connect=1

## REST `GET /fapi/v1/time` (ms)

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| keep-alive RTT | 1843 | 263 | 445 | 718 | 256 | 1526 | 292.8 |
| yeni bağlantı: TCP+TLS connect | 140 | 157 | 215 | 684 | 108 | 892 | 160.1 |
| yeni bağlantı: toplam (connect+istek) | 140 | 417 | 492 | 963 | 370 | 1233 | 428.8 |
| clock skew (server − local orta nokta) | 1843 | 0.5 | 62.5 | 191.0 | -172.0 | 486.0 | 9.0 |

### Keep-alive RTT saat bazında

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| 2026-09-10T07 | 712 | 261 | 347 | 485 | 256 | 734 | 273.1 |
| 2026-09-10T08 | 1131 | 265 | 488 | 878 | 257 | 1526 | 305.2 |

### Clock skew saat bazında

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| 2026-09-10T07 | 712 | 0.5 | 27.5 | 73.5 | -51.5 | 117.0 | 3.3 |
| 2026-09-10T08 | 1131 | 1.0 | 88.0 | 250.5 | -172.0 | 486.0 | 12.5 |

## WS /public bookTicker (ms)

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| btcusdt@bookTicker: recv − E | 122271 | 142 | 326 | 431 | 138 | 7142 | 167.2 |
| btcusdt@bookTicker: recv − T | 122271 | 143 | 326 | 431 | 138 | 7142 | 167.4 |
| ethusdt@bookTicker: recv − E | 89034 | 143 | 328 | 436 | 138 | 7151 | 174.9 |
| ethusdt@bookTicker: recv − T | 89034 | 143 | 328 | 436 | 138 | 7152 | 175.1 |
| json.loads süresi (µs) | 211305 | 5.7 | 18.6 | 28.9 | 3.1 | 130.5 | 7.5 |
| mesaj boyutu (byte) | 211305 | 203 | 204 | 204 | 200 | 205 | 203 |

Örneklenen kayıt: 211305. Toplam mesaj (sayaç): btcusdt@bookTicker=1222143, ethusdt@bookTicker=888771
Ortalama hız (msg/s, aktif saniyeler): btcusdt@bookTicker=289.33, ethusdt@bookTicker=210.41
Tepe saniye (kategori toplamı): 6615 msg/s

### /public bookTicker: recv − E saat bazında

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| 2026-09-10T07 | 90549 | 145 | 195 | 403 | 138 | 603 | 153.4 |
| 2026-09-10T08 | 120756 | 142 | 380 | 445 | 139 | 7151 | 183.2 |

## WS /market aggTrade + markPrice@1s (ms)

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| btcusdt@aggTrade: recv − E | 3902 | 140 | 256 | 426 | 137 | 468 | 156.8 |
| btcusdt@aggTrade: recv − T | 3902 | 211 | 432 | 565 | 140 | 917 | 238.5 |
| btcusdt@markPrice@1s: recv − E | 421 | 182 | 199 | 212 | 170 | 2751 | 190.8 |
| ethusdt@aggTrade: recv − E | 3322 | 139 | 159 | 418 | 137 | 2952 | 153.1 |
| ethusdt@aggTrade: recv − T | 3322 | 222 | 409 | 560 | 139 | 2968 | 239.7 |
| ethusdt@markPrice@1s: recv − E | 405 | 182 | 199 | 212 | 172 | 2572 | 192.7 |
| json.loads süresi (µs) | 8050 | 11.2 | 30.3 | 42.5 | 3.3 | 93.9 | 14.6 |
| mesaj boyutu (byte) | 8050 | 204 | 223 | 223 | 203 | 223 | 206 |

Örneklenen kayıt: 8050. Toplam mesaj (sayaç): btcusdt@aggTrade=39294, btcusdt@markPrice@1s=4226, ethusdt@aggTrade=32766, ethusdt@markPrice@1s=4226
Ortalama hız (msg/s, aktif saniyeler): btcusdt@aggTrade=9.30, btcusdt@markPrice@1s=1.00, ethusdt@aggTrade=7.76, ethusdt@markPrice@1s=1.00
Tepe saniye (kategori toplamı): 809 msg/s

### /market aggTrade + markPrice@1s: recv − E saat bazında

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| 2026-09-10T07 | 3320 | 144 | 202 | 426 | 137 | 445 | 160.8 |
| 2026-09-10T08 | 4730 | 139 | 207 | 425 | 137 | 2952 | 157.5 |

## WS API `depth` limit=5 (ms)

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| istek → cevap RTT | 802 | 277 | 283 | 286 | 271 | 767 | 278.1 |
| cevap alımı − E | 802 | 150 | 160 | 163 | 138 | 634 | 151.4 |

### WS API RTT saat bazında

| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| 2026-09-10T07 | 307 | 280 | 286 | 286 | 272 | 287 | 279.8 |
| 2026-09-10T08 | 495 | 274 | 281 | 285 | 271 | 767 | 277.0 |

Son `rateLimits`: `[{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 2400, "count": 14}]`
