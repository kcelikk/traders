# Faz durumu — tek doğruluk kaynağı

| Faz | Konu | Durum | Kapı |
|---|---|---|---|
| 0 | Ölçüm, build-vs-buy, unit economics, API doğrulama | **AKTİF** (başlangıç 2026-09-10) | Ölçüm raporu + ADR'ler onaylı, unit economics tutuyor |
| 1 | Temel + ham veri kaydı | bekliyor | 72 saat kesintisiz kayıt |
| 2 | Deterministik çekirdek + replay | bekliyor | bit-eşit replay testi CI'da |
| 3 | Offline araştırma (**DUR kapısı**) | bekliyor | maliyet üstü beklenti var mı |
| 4 | Pozisyon yönetimi ve çıkış | bekliyor | replay'de sabit TP/SL'ye göre iyileşme |
| 5 | Risk Engine | bekliyor | hata enjeksiyon testleri |
| 6 | Giriş mantığı | bekliyor | replay maliyet dahil pozitif |
| 7 | Paper trading (min 4 hafta) | bekliyor | backtest ile tutarlı |
| 8 | Gözlemlenebilirlik | bekliyor | tüm metrikler yayında |
| 9 | Testnet canlı execution | bekliyor | 2 hafta hatasız |
| 10 | Küçük sermaye canlı | bekliyor | proje sahibi onayı |

## Faz 0 ilerleme (2026-09-10)

| Teslim | Durum |
|---|---|
| Kurulum (python3-venv, make, venv, websockets 17.1, pytest 9.1.1) | tamam |
| `docs/binance-api-verification.md` | tamam — 2 kritik sapma: user data stream (ADR 0003), koşullu emirler Algo Service'e taşındı |
| Gecikme ölçümü | **sürüyor** — `baseline-24h-20260910`, başlangıç 07:33 UTC, 4 process; 1 saatlik ara rapor + 24 saat nihai |
| `docs/decisions/0001-build-vs-buy.md` | **onaylandı** (C: sıfırdan, ince yüzey) |
| `docs/unit-economics.md` | yazıldı; 3 girdi proje sahibinden bekleniyor |
| Proje sahibi kararları | ADR 0003 A onaylandı; ADR 0001 onaylandı; ADR 0004 kaydedildi (4 açık soru); komisyon kademesi bilinmiyor |

## Faz 0 kabul kriterleri

1. `docs/latency-baseline.md`: REST RTT (yeni bağlantı ve keep-alive ayrı), WS event→receive farkı (public ve market kategorisi ayrı), WS API istek→cevap, clock skew ve kayması. Her biri p50/p95/p99, en az 1 saat, hedef 24 saat.
2. `docs/binance-api-verification.md`: prompt BÖLÜM 4'teki her iddia için doğrulandı / değişti / bulunamadı kaydı, doküman URL'si ile.
3. `docs/decisions/0001-build-vs-buy.md`: karşılaştırma tablosu + net tavsiye.
4. `docs/unit-economics.md`: BÖLÜM 6.3 tablosu, maliyet dahil başabaş hesabı.
5. Proje sahibi onayı.

## Faz 0'da bilinçli olarak yapılmayanlar

- Docker kurulumu (Faz 1 başında ayrı onay)
- API anahtarı gerektiren her şey (kimlikli WS API gecikmesi Faz 9'a ertelendi)
- Trader kodu, gateway, çekirdek
