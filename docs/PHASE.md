# Faz durumu — tek doğruluk kaynağı

| Faz | Konu | Durum | Kapı |
|---|---|---|---|
| 0 | Ölçüm, build-vs-buy, unit economics, API doğrulama | **KAPANDI** 2026-09-10 (ölçüm ≥1 saat, ADR 0001/0003/0004 onaylı; 24 s ölçüm arka planda sürüyor) | Ölçüm raporu + ADR'ler onaylı, unit economics tutuyor |
| 1 | Temel + ham veri kaydı | **KAPANDI** 2026-09-10 (kapı raporu `docs/recording-gate-report.md`; kayıt sürüyor) | ≥1 saat kesintisiz kayıt (ADR 0006) |
| 2 | Deterministik çekirdek + replay | **KAPANDI** 2026-09-10 (proje sahibi onayı) | bit-eşit replay testi (`make test-determinism`) |
| 3 | Offline araştırma (**DUR kapısı**) | **AKTİF** (2026-09-10; kod yazıldı, veri birikiyor) | ADR 0008 §10 karar kuralı |
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

## Faz 1 ilerleme (2026-09-10)

| Teslim | Durum |
|---|---|
| Docker (docker.io 29.1.3, compose 2.40.3) | kuruldu, hello-world doğrulandı |
| Saf modüller (events, sequencer, universe, integrity, config) + writer + gateway | yazıldı, 46 test yeşil (sahte WS sunucusuyla yeniden bağlanma dahil) |
| Recorder container `fbot-recorder`, run `rec-72h` | başladı 2026-09-10 08:00 UTC, git 8271224, config 75a167d5a57d; **kapı 1 saat ile geçildi** (ADR 0006), kayıt sürüyor |
| 45 s yerel duman testi | 89.597 olay, seq boşluğu 0, SHA OK, loop lag p99 3.85 ms, ~370 MB/saat gzip |
| `scripts/verify_recording.py` | yazıldı; 2.75 saatlik kısmi kontrol: 10.9 M olay, seq boşluğu 0, 50 stream'de zincir kopuşu 0, loop lag p99 8.4 ms / maks 46.6 ms, kuyruk maks 569, ~220 MB/saat gzip |
| `fbot/orderbook.py` + `scripts/verify_orderbook.py` (kriter 7) | **doğrulandı** (ilk saat, 10 sembol): dokümandaki 9 kural ile local book kuruldu; sonraki REST snapshot'larla seviye eşitliği %96.9–99.7 (kalan fark: local book snapshot'tan ≤100 ms ileride); `pu` kopuşu 0; senkron kurulumu her snapshot'ta başarılı. Rapor `docs/orderbook-replay-hour1.md` |

**Replay bulgusu (Faz 2/4 girdisi):** başlangıçta REST snapshot ilk diff olayından eski kalınca (`U > lastUpdateId`, "gap") senkron sonraki periyodik snapshot'a kadar (≤10 dk) kurulamıyor; recorder için sorun değil ama trader gateway'i resync'te snapshot'ı **hemen** yeniden çekmeli (ağırlık 20, 2400/dk limiti içinde).

## Faz 1 — hedef

TOP 10 sembolün ham market verisini kategori bazlı WS bağlantılarından tek sıralama noktasıyla geçirip append-only, sıkıştırılmış ve bütünlüğü doğrulanabilir biçimde diske kaydetmek; Docker altında 72 saat kesintisiz çalıştırmak. Bu kayıt Faz 2 replay'in ve Faz 3 araştırmasının tek girdisidir.

## Faz 1 — kabul kriterleri

1. `docker compose up -d recorder` ile başlar; `/public` ve `/market` için ayrı bağlantı; 10 sembol × 5 stream.
2. Her olay monoton `seq` taşır; `scripts/verify_recording.py` raporunda **seq boşluğu = 0, seq tekrarı = 0**.
3. Her dosyanın SHA-256'sı manifest ile eşleşir; kesilmiş/bozuk gzip yok.
4. Stream düzeyi bütünlük raporlanır: aggTrade `a` ardışıklığı, bookTicker `u` monotonluğu, depth `pu == önceki u` zinciri; kopuş sayıları ve nedenleri (reconnect ile eşleşme) listelenir.
5. Reconnect sayısı, kategori bazlı bayatlık olayları, snapshot sayısı, loop lag (p50/p99/max) ve kuyruk derinliği raporlanır.
6. Kayıt **en az 1 saat** kesintisiz (ADR 0006; eski kural 72 saat). Process yeniden başlasa bile run manifest'i devam eder; her restart raporda görünür.
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

## Faz 2 ilerleme (2026-09-10)

| Kriter | Sonuç |
|---|---|
| 1 Saflık | `tests/test_purity.py` AST taraması geçiyor; çekirdek modüllerinde yasak import yok |
| 2 Bit-eşitlik | fixture iki ayrı process: hash eşit. Gerçek kayıt ilk saat (3.471.623 olay) iki kez: hash `f3db4dba4ed5c6ef…` eşit, 560 `BarClosed` (10 sembol × 56 dk) |
| 3 Negatif test | aggTrade miktarında tek basamak değişimi → hash farklı |
| 4 Bar doğruluğu | sentetik OHLCV/işlem sayısı testi; kova sınırı `T` ile |
| 5 Bayatlık | kategori bazlı eşik ve geri dönüş testi; gerçek kaydın ilk saatinde bayatlık olayı 0 |
| 6 Maliyet modeli | komisyon/funding/slippage `Decimal`, config'den; 4 test |
| 7 Execution arayüzü | Paper/Replay kaydediyor; Live stub `RuntimeError` (test) |
| 8 Replay hızı | **~65.000 olay/s** (tek çekirdek, JSON çözümü dahil); ilk saat 54 s |
| 9 Dokümanlar | README, CLAUDE.md, ADR 0007 güncel |

Toplam 75 test. `make test-determinism` yeşil. **Faz 2 kapandı** (proje sahibi onayı, 2026-09-10).

## Faz 2 — hedef

Rule Zero'ya uygun saf çekirdek (`step(state, event, now_ns) -> (state, commands)`), `Clock` soyutlaması, kayıt formatını okuyan replay harness, `Decimal` tabanlı maliyet modeli ve execution adapter arayüzü (Live korumalı stub). Strateji yok; çekirdek piyasa görünümü, 1 dk bar ve bayatlık türetir.

## Faz 2 — kabul kriterleri

1. **Saflık:** `fbot/core/*`, `fbot/costs.py`, `fbot/clock.py` yasak modül import etmez; `tests/test_purity.py` AST ile tarar ve geçer.
2. **Bit-eşitlik:** mini fixture (`tests/fixtures/rec-mini/`) iki ayrı process'te oynatıldığında komut hash'i aynı; `make test-determinism` yeşil. Gerçek kaydın ilk saati de iki kez oynatılır, hash eşit (`make replay`).
3. **Negatif test:** fixture'da tek olay değiştirilince hash değişir.
4. **Bar doğruluğu:** sentetik aggTrade dizisinden OHLCV ve işlem sayısı beklenen değerlerle eşleşir; kova sınırı `T` ile.
5. **Bayatlık:** kategori bazlı eşik aşımı ve geri dönüş `StalenessChanged` üretir; replay'de `recv_ns` ile.
6. **Maliyet modeli:** komisyon (maker/taker/BNB), funding (yön işareti), slippage (defter yürüyüşü) testli; oranlar config'den; `Decimal`.
7. **Execution arayüzü:** Paper/Replay adapter komutları kaydeder; `LiveExecutionAdapter` her çağrıda hata fırlatır (test).
8. Replay hızı (olay/s) ölçülür ve raporlanır.
9. README ve CLAUDE.md komutları güncel.

## Faz 2 — dosya ağacı

```
fbot/
  clock.py                # Clock protokolü, ReplayClock (saf)
  costs.py                # maliyet modeli (saf, Decimal)
  core/
    __init__.py
    commands.py           # BarClosed, StalenessChanged, canonical()
    market.py             # SymbolMarket: best bid/ask, son işlem, mark/funding, bar üretici
    engine.py             # CoreState, CoreConfig, Engine.step
  replay/
    __init__.py
    harness.py            # kayıt okuma, ReplayClock, hash zinciri, hız ölçümü
  execution/
    __init__.py
    adapter.py            # ExecutionAdapter, Paper/Replay/Live(stub)
scripts/replay.py         # CLI: özet JSON
tests/fixtures/rec-mini/  # ilk 5 dk, market + ctrl olayları (public 1/100 örnekli)
tests/test_purity.py test_clock.py test_commands.py test_market_bars.py test_engine.py test_costs.py test_execution.py test_replay_determinism.py
```

## Faz 3 — hedef

Kayıtlı veri üzerinde en fazla 5 piyasa durumu tanımlamak ve her durumdan sonraki ileriye dönük **net** (maliyet dahil) getiri dağılımını ölçmek. Tek soru: herhangi bir (durum, ufuk, yön) hücresi doğrulama bölümünde maliyeti aşan beklenti üretiyor mu? Hayırsa proje durur (DUR kapısı). Metodoloji: ADR 0008. Hipotezler: `docs/research/hipotezler.md`.

## Faz 3 — kabul kriterleri

1. **Look-ahead yok:** feature'lar `T ≤ bar.end_ms` verisinden; kesme testi bit-eşit (`tests/test_features_lookahead.py`).
2. **Determinizm:** aynı kayıt + aynı config + aynı seed → aynı rapor (hash).
3. **Maliyet her hücrede:** komisyon, ölçülen spread, defter slippage'ı, ufku kesen funding. Maliyetsiz sütun yok.
4. **Örtüşmeyen örnekleme** ve **keşif/doğrulama (%70/%30, zaman bazlı)** raporda ayrı.
5. **Karar hücresi kuralı** (ADR 0008 §8): doğrulamada bootstrap %95 CI alt sınırı > 0, n ≥ 100, keşifte de anlamlı.
6. **Rapor:** `docs/research/rapor-<run>.md`, hücre tablosu + durum süre dağılımı + geçiş matrisi + sembol kırılımı; ön rapor ≥24 s, nihai ≥3 gün.
7. **Karar:** Faz 4'e geçiş ya da DUR, proje sahibine açık gerekçeyle.

## Faz 3 ilerleme (2026-09-10)

| Teslim | Durum |
|---|---|
| `fbot/research/` (features, states, forward, stats) | yazıldı; 12 test (kesme testi, durum kuralları, getiri matematiği, seed'li bootstrap) |
| `BarClosed.buy_volume` | çekirdeğe eklendi (imb feature'ı için); determinizm testleri yeşil |
| `scripts/export_bars.py`, `scripts/research_report.py`, `config/research.toml` | yazıldı; `make export-bars`, `make research-report` |
| Ön çalıştırma (4.9 saat, 10 sembol) | 28.6 M olay → 2.960 bar (7.4 dk); rapor `docs/research/rapor-rec-72h.md`; etiketli bar S1 14 / S2 11 / S3 11 / S4 0 → **yetersiz veri**, karar yok |
| Toplam test | 87 |

Sonraki adım: ≥24 saat kayıtla ön rapor (2026-09-11), ≥3 günle nihai rapor ve DUR kararı (2026-09-13 sonrası).

## Faz 3 — dosya ağacı

```
fbot/research/
  __init__.py
  features.py        # bar dizisinden rolling feature'lar ve persentiller (saf)
  states.py          # S0–S4 etiketleme (saf; Faz 6'da çekirdeğe taşınır)
  forward.py         # ileriye dönük brüt/net getiri, örtüşmeyen örnekleme (saf)
  stats.py           # seed'li bootstrap CI, özet istatistik (saf)
scripts/export_bars.py     # replay → bar + spread + funding serisi (JSONL)
scripts/research_report.py # rapor üretimi
config/research.toml       # W, p_lo, p_hi, ufuklar, maliyet senaryoları, seed, keşif oranı
tests/test_features_lookahead.py test_states.py test_forward_returns.py test_stats.py
```
