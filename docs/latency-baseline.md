# Gecikme temel ölçümü — ARA RAPOR (ilk 1 saat)

Run: `baseline-24h-20260910`, başlangıç 2026-09-10 07:39 UTC, süre 24 saat (sürüyor). Bu rapor ilk ~1 saati kapsar; **nihai rapor 24 saat sonunda bu dosyanın üzerine yazılır.** Tam tablolar: `docs/latency-baseline.generated.md` (`make summarize-latency`).

Yöntem: kategori başına ayrı process (yerel kuyruklanma ölçüme karışmasın diye; tek process'te p95 943 ms görülmüştü, ayrı process'te 163 ms). Sunucu: `srv`, Ubuntu 24.04, NTP senkron. Semboller BTCUSDT, ETHUSDT. WS örnekleme 1/10, hız sayaçları tam.

## Sonuçlar (ms)

| Ölçüm | n | p50 | p95 | p99 | maks |
|---|---|---|---|---|---|
| REST `GET /fapi/v1/time`, keep-alive RTT | 1816 | 263 | 447 | 718 | 1526 |
| TCP+TLS bağlantı kurma | 138 | 157 | 216 | 684 | 892 |
| Yeni bağlantı toplam (connect + istek) | 138 | 417 | 498 | 963 | 1233 |
| Clock skew (server − yerel orta nokta) | 1816 | 0.5 | 63.5 | 191 | 486 |
| `/public` bookTicker BTC, recv − E | 120761 | 142 | 325 | 431 | 7142 |
| `/public` bookTicker ETH, recv − E | 88344 | 143 | 327 | 436 | 7151 |
| `/market` aggTrade BTC, recv − E | 3866 | 140 | 265 | 427 | 468 |
| `/market` aggTrade BTC, recv − T (işlem zamanı) | 3866 | 211 | 432 | 566 | 917 |
| `/market` markPrice@1s, recv − E | 414 | 181 | 199 | 212 | 2751 |
| WS API `depth` limit=5, istek → cevap | 790 | 277 | 283 | 286 | 767 |
| WS API cevap alımı − E | 790 | 150 | 160 | 163 | 634 |

Mesaj hızı (2 sembol): bookTicker ort. 290 + 212 msg/s, **tepe 6615 msg/s**; aggTrade 9.4 + 7.8 msg/s, tepe 809. `json.loads` p99 29 µs (bookTicker), 43 µs (aggTrade). Yeniden bağlanma: 0. Hata: 0.

Saat bazında `/public` recv − E: 07:xx p95 195 / p99 403; 08:xx p95 380 / p99 445, maks 7.1 s. 08:00'de aynı makinede recorder container'ı başladı; kuyruk tepesinin makine yükünden mi ağdan mı geldiği 24 saatlik seriden ayrıştırılacak.

## Yorum

1. **Tek yön ağ gecikmesi ≈ 75–80 ms.** TCP bağlantı kurma (1 RTT) p50 157 ms. bookTicker recv − E p50 142 ms = tek yön + Binance yayın gecikmesi (+ skew ≈ 0).
2. **aggTrade'de E − T ≈ 70 ms.** Eşleşme anından yayına Binance içi gecikme. Fiyat tetikleyicileri için `T` değil `E` ve alım zamanı esas alınmalı; feature hesaplarında hangi zaman damgasının kullanıldığı açıkça yazılır.
3. **Tepki döngüsü (veri alımı → karar → emir ACK):** p50 ≈ 142 + 277 ≈ **420 ms**, p99 ≈ 431 + 286 + kuyruk ≈ **0.9–1 s**; tek kötü saniyede 7 s.
4. **Clock skew** p99 191 ms, maks 486 ms. `recvWindow` varsayılanı 5000 ms bu ölçümde yeterli; ölçüm bitmeden config'e yazılmaz.
5. **Mesaj yükü:** 2 sembolde 6.6k msg/s tepe. 10 sembolde tepeler 10k+ olabilir; recorder'ın loop lag'i 72 saatlik kayıttan okunacak. Hot path'te bookTicker'ı her mesajda işlemek yerine "son değer" semantiğiyle çökertme (conflation) Faz 2 tasarım konusu.

## Faz 0 çıktıları için ön değerler (24 saat sonunda kesinleşir)

| Parametre | Ön değer | Gerekçe |
|---|---|---|
| Uçtan uca gecikme (planlama) | p50 0.42 s, p99 ~1 s | tepki döngüsü |
| Minimum sinyal ufku (≥ 10 × gecikme) | **≥ 10 s** (p99 esas) | saniye altı sinyaller elenir |
| Minimum anlamlı feature penceresi | ≥ 10 s; bar bazlı feature'lar için ≥ 1 dk | ufuk kuralı |
| Uygulama tarafı çıkış vs borsa tarafı | 1 s içinde %0.1'den hızlı hareketlerde borsa tarafı stop tek güvenilir koruma; uygulama çıkışı yalnızca yavaş bozulma için | tepki döngüsü p99 |
| `recvWindow` | 5000 (varsayılan) | skew maks 486 ms |
| Bayatlık eşiği (public/market) | henüz sabitlenmedi | 24 saatlik en uzun sessizlik ölçülecek |

## Yapılmayanlar

- 24 saat tamamlanmadı; gün içi ve funding saatleri kapsanmadı.
- Kimlikli WS API (`session.logon` sonrası `order.place`) gecikmesi ölçülmedi (anahtar gerekir, Faz 9).
- 08:xx'teki kuyruk tepesinin kaynağı ayrıştırılmadı.
