# Faz durumu — tek doğruluk kaynağı

| Faz | Konu | Durum | Kapı |
|---|---|---|---|
| 0 | Ölçüm, build-vs-buy, unit economics, API doğrulama | **AKTİF** (başlangıç 2026-09-10) | Ölçüm raporu + ADR'ler onaylı, unit economics tutuyor |
| 1 | Temel + ham veri kaydı | **AKTİF** (2026-09-10, proje sahibi talimatıyla; Faz 0 kapanışı 24 s ölçüm raporuna bağlı) | 72 saat kesintisiz kayıt |
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
| Proje sahibi kararları | ADR 0003 A onaylandı; ADR 0001 onaylandı; ADR 0004 kabul edildi (80 USDT notional, TOP 10 günlük, BTC/ETH 10x diğerleri 5x, SL/TP Faz 3); komisyon kademesi bilinmiyor |

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

## Faz 1 — hedef

TOP 10 sembolün ham market verisini kategori bazlı WS bağlantılarından tek sıralama noktasıyla geçirip append-only, sıkıştırılmış ve bütünlüğü doğrulanabilir biçimde diske kaydetmek; Docker altında 72 saat kesintisiz çalıştırmak. Bu kayıt Faz 2 replay'in ve Faz 3 araştırmasının tek girdisidir.

## Faz 1 — kabul kriterleri

1. `docker compose up -d recorder` ile başlar; `/public` ve `/market` için ayrı bağlantı; 10 sembol × 5 stream.
2. Her olay monoton `seq` taşır; `scripts/verify_recording.py` raporunda **seq boşluğu = 0, seq tekrarı = 0**.
3. Her dosyanın SHA-256'sı manifest ile eşleşir; kesilmiş/bozuk gzip yok.
4. Stream düzeyi bütünlük raporlanır: aggTrade `a` ardışıklığı, bookTicker `u` monotonluğu, depth `pu == önceki u` zinciri; kopuş sayıları ve nedenleri (reconnect ile eşleşme) listelenir.
5. Reconnect sayısı, kategori bazlı bayatlık olayları, snapshot sayısı, loop lag (p50/p99/max) ve kuyruk derinliği raporlanır.
6. Kayıt **en az 72 saat** kesintisiz (process yeniden başlasa bile run manifest'i devam eder; her restart raporda görünür).
7. Depth snapshot + diff zinciri ile local order book replay'de en az bir sembol için doğrulanır (ilk event koşulu `U <= lastUpdateId <= u`).
8. Testler: saf modüller birim testli; sahte WS sunucusuyla kopma/yeniden bağlanma entegrasyon testi geçiyor; `make test` yeşil.
9. README güncel; komut çıktıları teslimde gösterilir.

## Faz 1 — dosya ağacı

```
fbot/
  __init__.py
  config.py            # TOML yükleme, doğrulama, hash (saf + dosya okuma)
  events.py            # RawEvent, encode/decode — ham bayt korunur (saf)
  sequencer.py         # tek sıralama noktası (saf)
  universe.py          # TOP N kuralı, sembol filtreleri (saf)
  integrity.py         # seq / stream bütünlük denetimleri (saf)
  gateway/
    ws_category.py     # kategori bağlantı yöneticisi: bağlan, yeniden bağlan, bayatlık (I/O)
    rest.py            # exchangeInfo, ticker/24hr, depth snapshot (I/O, stdlib)
  recorder/
    writer.py          # saatlik gzip rotasyon, manifest (I/O)
    main.py            # process giriş noktası
scripts/verify_recording.py
config/recorder.toml
docker/Dockerfile
docker-compose.yml
tests/test_events.py test_sequencer.py test_universe.py test_integrity.py test_config.py test_writer.py test_gateway_reconnect.py
```
