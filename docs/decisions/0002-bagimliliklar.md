# ADR 0002 — Faz 0 bağımlılıkları

Tarih: 2026-09-10 · Durum: kabul edildi

## Bağlam
Faz 0 yalnızca ölçüm yapar. Sistem Python'ı (3.12.3) kirletilmez; venv kullanılır. Her bağımlılık gerekçelendirilir (prompt 0.6).

## Sistem paketleri
| Paket | Ne çözüyor | Alternatif | Karar |
|---|---|---|---|
| python3-venv | Ubuntu 24.04'te `ensurepip` yok, venv kurulamıyordu | uv (ek indirme, ek araç) | apt paketi, minimum |
| make | Tekrar edilebilir komutlar | shell betikleri | Makefile; prompt BÖLÜM 1 |
| docker | — | — | Faz 0'da gerekmiyor, Faz 1'de ayrı onay |

## Python paketleri
| Paket | Sürüm | Ne çözüyor | Alternatif | Bakım |
|---|---|---|---|---|
| websockets | 17.1 | stdlib'de WS istemcisi yok; asyncio uyumlu, tek thread | aiohttp (daha geniş yüzey, HTTP de getirir) | aktif, yaygın |
| pytest | 9.1.1 | test önce yazılır kuralı | unittest (stdlib, daha zahmetli) | aktif |

REST istekleri stdlib `urllib`/`http.client` ile yapılır; ek HTTP kütüphanesi eklenmez.

## Sonuçlar
- Gateway'de aynı `websockets` kütüphanesi kullanılacaksa Faz 1'de tekrar değerlendirilir (ping/pong davranışı, mesaj boyutu limitleri dokümandan doğrulanır).
- Sürümler `requirements.txt` içinde sabitlenmiştir.
