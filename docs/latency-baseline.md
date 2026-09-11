# Gecikme temel ölçümü — NİHAİ (24 saat)

Run `baseline-24h-20260910`, 2026-09-10 07:39 → 2026-09-11 07:45 UTC, **24.11 saat**. Ham veri `data/latency/`, tam tablolar `docs/latency-baseline.generated.md` (`make summarize-latency`).

Yöntem: kategori başına ayrı process (tek process'te yerel kuyruklanma ölçüme karışıyordu). Semboller BTCUSDT, ETHUSDT. WS örnekleme 1/10, hız sayaçları tam. Kopma: 1 public disconnect, 1 REST bağlantı hatası; 24 saatte toplam 2 yeniden bağlanma.

## Sonuçlar (ms)

| Ölçüm | n | p50 | p95 | p99 | maks |
|---|---|---|---|---|---|
| REST `GET /fapi/v1/time`, keep-alive RTT | 38.028 | 264 | 355 | 680 | 7.930 |
| TCP+TLS bağlantı kurma | 2.850 | 151 | 216 | 701 | 10.125 |
| Yeni bağlantı toplam | 2.850 | 414 | 523 | 1.010 | 10.383 |
| Clock skew (server − yerel) | 38.028 | 2.0 | 27.5 | 164.5 | 793 |
| `/public` bookTicker, recv − E | 3.149.529 | 150 | 324 | 606 | 22.376 |
| WS API `depth`, istek → cevap | 16.430 | 276 | 287 | 298 | 797 |
| WS API cevap alımı − E | 16.430 | 151 | 163 | 170 | 660 |
| `json.loads` (µs) | 5.975.237 | 4.9 | 15.3 | 26.9 | 17.646 |

## 1 saatlik ara raporla fark

p50'ler değişmedi (142 → 150 ms). Kuyruk uçları kötüleşti: public p99 431 → 606 ms, maksimum 7.1 s → 22.4 s. Yani **gün içinde nadir ama çok uzun duraklamalar var** ve bir saatlik ölçüm bunları göremiyor.

En kötü saatler (public recv − E): 12:00 UTC p99 4.091 ms, 16:00 UTC p99 3.426 ms. İkisi de ABD/Avrupa yoğun saatleri. Sakin saatlerde p99 550 ms civarı.

## Sabitlenen parametreler

| Parametre | Değer | Gerekçe |
|---|---|---|
| Tek yön ağ gecikmesi | ≈ 75 ms | TCP kurulum p50 151 ms |
| Tepki döngüsü (veri → karar → ACK) | p50 ≈ 0.43 s · p99 ≈ 0.9 s · tepe > 20 s | recv−E + WS API RTT |
| Minimum sinyal ufku | **≥ 10 s** (p99 × 10) | saniye altı sinyaller elenir |
| `recvWindow` | **5000 ms** | skew p99 165 ms, maks 793 ms; 6 kat pay |
| Bayatlık eşiği, public/market | **30 s** | en uzun olaysız aralık 22.4 s; eşik bunun üstünde, 60 s gereksiz geç |
| Koruma emri gerekliliği | değişmedi | 20 s'lik duraklamada uygulama tarafı çıkış yetişmez; borsa tarafı stop zorunlu |

## Yapılmayanlar

- Kimlikli WS API (`session.logon` sonrası `order.place`) gecikmesi ölçülmedi; anahtar gerektiriyor, Faz 9'da testnet ile ölçülecek.
- 22 s'lik tepenin kaynağı ayrıştırılmadı (ağ, Binance yayın tarafı ya da yerel GC). Kayıt tarafındaki `loop_lag` aynı anda düşük olduğu için yerel kuyruklanma değil.
- Ölçüm tek gün; funding saatleri ve haftasonu davranışı kapsanmadı.
