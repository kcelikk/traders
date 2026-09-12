# Faz durumu — tek doğruluk kaynağı

| Faz | Konu | Durum | Kapı |
|---|---|---|---|
| 0 | Ölçüm, build-vs-buy, unit economics, API doğrulama | **KAPANDI** 2026-09-10; **24 saatlik ölçüm tamamlandı 2026-09-11** (`docs/latency-baseline.md`: bayatlık 30 s, recvWindow 5000, ufuk ≥10 s) | Ölçüm raporu + ADR'ler onaylı, unit economics tutuyor |
| 1 | Temel + ham veri kaydı | **KAPANDI** 2026-09-10 (kapı raporu `docs/recording-gate-report.md`; kayıt sürüyor) | ≥1 saat kesintisiz kayıt (ADR 0006) |
| 2 | Deterministik çekirdek + replay | **KAPANDI** 2026-09-10 (proje sahibi onayı) | bit-eşit replay testi (`make test-determinism`) |
| 3 | Offline araştırma (bilgilendirici) | **KAPANDI** 2026-09-10: 0/48 hücrede maliyet üstü beklenti; kapı kaldırıldı (ADR 0010); araştırma paralelde sürer | — |
| 4 | Pozisyon yönetimi ve çıkış | **KAPANDI** 2026-09-10 (ADR 0012) | replay'de sabit TP/SL'ye göre iyileşme |
| 5 | Risk Engine | **KAPANDI** 2026-09-10 (ADR 0014): 2026-09-10: assess K1–K18, runaway, kalıcı kill switch, mutabakat; çekirdeğe bağlandı (giriş zinciri) | hata enjeksiyon testleri |
| 6 | Giriş mantığı | **KAPANDI** 2026-09-10 (ADR 0014): 2026-09-10: State Engine çekirdekte (araştırma ile bit-eşit), Decision Engine D1–D3, zincir bağlı; `allowed_cells` boş (Faz 3: 0/48) | replay maliyet dahil pozitif |
| 7 | Paper trading (2 hafta ara rapor, 4 hafta hedef) | **AKTİF** 2026-09-10: `fbot-paper` container'ı izole çalışıyor (demo config, strateji değil) | backtest ile tutarlı |
| 8 | Gözlemlenebilirlik | **kısmen başladı** 2026-09-10: fbot Console (ui/ + fbot/api, kayıt tail, /api/state, kill switch); Prometheus/Grafana/alarmlar bekliyor | tüm metrikler yayında |
| 9 | Testnet execution | **AKTİF** 2026-09-10 (proje sahibi onayı): izole servis; emir durum makinesi + rate limiter + imzalama yazılıyor | 2 hafta hatasız |
| 10 | Küçük sermaye canlı | bekliyor (tasarım notu: `docs/design/faz10-kucuk-sermaye-canli.md`) | proje sahibi onayı |

## Mimari refactor gate'leri (2026-09-12 →)

Fazlardan bağımsız, execution katmanını üretime hazır hâle getiren ve üstüne strateji platformu
kuran iş. Yeni alpha geliştirmesi değildir: entry mantığı, durum tanımları ve `allowed_cells`
değişmez.

| Gate | Konu | Durum | Çıkış koşulu |
|---|---|---|---|
| 0 | Test harness, golden baseline, benchmark kapısı, testnet davranış doğrulaması | **KAPANDI** 2026-09-12 (`docs/binance-api-gate0-dogrulama.md`) | golden + bench baseline sabitlendi; `fbot/` değişmedi |
| 1 | Veri yolu ve kimlik: koşu kimliği, asenkron kalıcılık, rol bazlı stream profilleri | **teslim edildi 2026-09-12, proje sahibi onayı bekliyor** (ADR 0017, ölçüm `docs/gate1-olcum.md`) | **hash-nötr**: golden hash değişmedi ✓ |
| 2 | 2.0 çekirdek doğruluk düzeltmeleri (**re-baseline #1**) + 2.1 bloklamayan execution transport | **teslim edildi 2026-09-12, onay bekliyor** (ADR 0018, ADR 0019; ölçüm `docs/gate2-olcum.md`) | re-baseline farkı yalnız `trigger_price` / `client_id` / `client_algo_id` ✓ |
| 3 | Exchange truth: user data akışı (shadow), emir kaydı, çıkış kilidi, orphan/koruma onarımı (dry-run), balance mutabakatı | **teslim edildi 2026-09-12, onay bekliyor** (ADR 0020; gözlem `docs/gate3-userdata-gozlem.md`) | **hash-nötr** ✓ (iki golden de değişmedi) |
| 4 | Reactor, güvenlik katmanları, metrikler | bekliyor | re-baseline #2 (bayatlıkta çıkış kuralları) + shadow→active ayrı onay |
| 5 | Strateji platformu: kayıt, versiyonlama, replay→paper→testnet→live terfi | bekliyor | — |

## Gate 2 teslimi (2026-09-12)

| Teslim | Durum |
|---|---|
| `fbot/core/rounding.py` — tek yuvarlama noktası, kaynak `Filters` (pricePrecision değil) | tamam |
| `fbot/core/ids.py` — kimlik grameri, uzunluk girdiden bağımsız (`-4015` kapandı) | tamam |
| `pending_entries` TTL + ret/bilinmeyen sonuçta bırakma | tamam |
| `testnet_adapter` — `_fmt` ve `ROUND_HALF_EVEN` gitti; filtresiz sembolde fail-closed | tamam |
| Emir düzeyi golden (`tests/golden/orders_baseline.json`) + fark tablosu | tamam; **re-baseline #1** yapıldı |
| `fbot/gateway/http_pool.py` — kalıcı bağlantı, ayrı connect/read bütçesi, kör retry yok | tamam; canlıda 1 bağlantı / 9 istek |
| `fbot/execution/queue.py` — sınırlı kuyruk, sınıf bazlı rezerv, FIFO | tamam |
| Taşıma hatası sınıflandırması (POST timeout → UNKNOWN + mutabakat) | tamam |
| 429 `Retry-After`, 418 ban + geri çekilme | tamam |
| Periyodik silahlanma/mutabakat `to_thread`'e taşındı | tamam |
| `[execution] transport` anahtarı (geri alma: `legacy`) | tamam |
| Test | 527 → 557 |

**Gate 2'de çıkan canlı hata:** gönderim kuyruğu `Recorder.queue`'yu (olay yazım kuyruğu)
gölgeliyordu; testnet süreci açılışta düştü. Testler yakalamıyordu çünkü `TestnetRecorder` hiçbir
testte kurulmuyor. Alan adı `exec_queue` oldu, regresyon testi eklendi.

## Gate 3 teslimi (2026-09-12)

| Teslim | Durum |
|---|---|
| `fbot/gateway/userdata.py` — listenKey yaşam döngüsü, keepalive yöneticinin parçası (ADR 0003) | tamam; canlıda bağlı, **shadow** |
| `CategoryConnection.url_factory` — private için ikinci sınıf yazılmadı | tamam |
| Private çerçeveler tek sıralama noktasından kayda | tamam; gerçek emirle kanıtlandı |
| `fbot/core/oms.py` — saf emir kaydı, `cid → pos_id/rol`, niyet defteri, UNKNOWN TTL | tamam |
| Çekirdek borsa emir olaylarını çözüyor (`order_ack/fill/done`) | tamam; **mod shadow olduğu için canlıda tüketilmiyor** |
| Çıkış kilidi (`exit_in_flight`) + TTL, tam çıkışta filtre, sürüm geri yükleme | tamam |
| Sahipsiz emir iptali — **yalnız bizim gramerimiz**, `dry_run` | tamam; canlıda plan boş |
| Korumasız pozisyon onarımı — bilinen pozisyon için, `dry_run` | tamam |
| Bakiye/teminat snapshot'ı, HEDGE'te emir yolu kapanışı, `positionSide=BOTH`, iptal doğrulaması | tamam |
| `-2022` → UNKNOWN (ADR 0020, faz4 §9 supersede) | tamam |
| `trade_id` / `order_id` eşlemesi (dedupe sessizce çalışmıyordu) | tamam |
| Test | 573 → 627 |

**Gate 3'te çıkan ölçüm bulgusu:** testnet hesabı **çoklu varlık teminat** modunda; `availableBalance`
USDT dışı bakiyeyi de içeriyor (4.208 cüzdan / 9.892 available, fark USDC). Büyüklük hesabı
muhafazakâra çekildi; mainnet hesabının modu **proje sahibi kararı**.

**Gate 3'te onay bekleyen kapılar:** `[userdata] mode = "active"` (çekirdeğin tüketmesi),
`orphan_cancel = "apply"`, `protect_repair = "apply"`. Üçü de bugün kapalı.

## Gate 4 teslimi (2026-09-12)

| Teslim | Durum |
|---|---|
| `fbot/core/health.py` — ortogonal gerçekler, `exit_mode` FULL/PROTECTION_ONLY/HALTED | tamam; `FROZEN` blanket kalktı |
| `fbot/core/reactors.py` — olay-tetiklemeli değerlendirme, **shadow**, ayrı hash zinciri | tamam; `active` yapılandırma hatası veriyor |
| `CoreState.by_symbol` indeksi | tamam; açık pozisyon yoksa reactor O(1) |
| Reactor bütçesi (`make bench-reactors`) | **medyan +%8,8**, bütçe +%20 (6 koşu, 1.048 niyetle doğrulandı) |
| `fbot/core/breaker.py` — günlük net zarar, ardışık zarar, `alarm` modu | tamam; eşik ölçülmüş değil, seçilmiş |
| `RunawayDetector` kurulumu + 418 → kalıcı kill switch | tamam; ikisi de ölü yoldu |
| `fbot/core/telemetry.py` — sabit kovalı histogram, yaklaşık persentil | tamam; RTT ve user data gecikmesi bağlı |
| `scripts/rebaseline_report.py` (`make rebaseline`) — giriş farkı sıfır kapısı | tamam |
| Test | 661 → 675 |

**Gate 4'te onay bekleyen kapı:** `[reactors] mode = "active"`. Shadow gözlemi pozisyon açılmadığı
için henüz veri toplayamadı.

**Gate 0 bulgusu (açık, Gate 2/3):** aynı yönde ikinci `closePosition` koruma emri `-4130` ile
reddediliyor; R3 trailing kuralı gerçek borsada önce yeni SL gönderip sonra eskisini iptal ettiği
için pozisyonu **korumasız bırakır**. `allowed_cells` boş olduğu için bugün tetiklenmiyor.

## Gate 1 teslimi (2026-09-12)

| Teslim | Durum |
|---|---|
| `fbot/identity.py` + `runs` tablosu + satır bazlı kimlik sütunları (tek `ADD COLUMN` göçü) | tamam; canlı `paper.db` ve `testnet.db` göç etti, satır kaybı yok |
| `fbot/persistence/writer.py` (`AsyncStore`): sınırlı kuyruk + yazıcı görevi + `to_thread` | tamam; hot path'te SQLite ifadesi **0** (trace ile test edildi) |
| `PaperTrader._record_positions` kirli-bayrak + tick tazeleme | tamam |
| `[streams] profile` (recorder / trader_paper / trader_testnet), fail-closed depth denetimi | tamam; `fbot-paper` ve `fbot-testnet` yeni imajla yeniden başlatıldı |
| `config_semantic_hash` (etkin değerlerin hash'i) | tamam |
| `CoreState` yinelenen alanları ve `_risk_inputs` yinelenen bloğu | silindi; golden hash değişmedi |
| Ölçüm | `docs/gate1-olcum.md` |
| Test | 472 → 495 |

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

## Faz 4 ilerleme (2026-09-10) — teslim edildi, onay bekliyor

| Kriter | Sonuç |
|---|---|
| 1–4 durum makinesi, kurallar, değiştirme sırası | `fbot/core/position.py`, 10 test |
| 5 deterministik id'ler | `p1-SL-v1`, `p1-TP-v1`, `p1-X-v1`; ≤ 36 karakter |
| 6 net PnL | komisyon + funding (markPrice `T` değişiminde işlenir) + slippage tahmini; `Decimal` |
| 7 engine exec/tick | `exec` olayları ve `ctrl/tick`; bayatlıkta FROZEN; 139 test yeşil, determinizm korunuyor |
| 8 recorder tick | `tick_ms=1000`; container yeniden başlatıldı (restart 1, seq devam) |
| 9 replay karşılaştırması (bilgilendirici) | 9 saat, S1/S2 girişleri, SL 0.5 / TP 1.0, 80 USDT, taker/taker — aşağıda |
| ek | user data payload doğrulaması (§12) ve `exec` eşlemesi; dolum simülatörü (Faz 7 çekirdeği); parse hızı 10k → 67k olay/s |

Replay karşılaştırması (`docs/design/faz4-replay-karsilastirma.md`):

| ölçüt | statik SL/TP | statik + R1/R3/R5 |
|---|---|---|
| pozisyon | 87 | 143 |
| net ort. / pozisyon | −0.245 % | −0.187 % |
| kazanma oranı | 24 % | 36 % |
| kârdayken (> +0.10 % net) zararla kapanan oranı | **67 %** | **44 %** |
| SL değiştirme sayısı | 0 | 140 |
| çıkış nedenleri | tp 21, sl 66 | sl 121, tp 11, timeout 11 |

Yorum: kâr kilidi kârdan zarara dönmeyi belirgin düşürüyor ve pozisyon başına net sonucu iyileştiriyor; ancak girişlerde avantaj olmadığı için (Faz 3) daha çok işlem = daha çok komisyon, toplam yine negatif. Çıkış mekaniği tasarlandığı işi yapıyor; kârlılık girişe bağlı. **Kârlılık gösterilmedi.**

## Faz 4 — hedef

Strateji-bağımsız pozisyon yönetimi: pozisyon durum makinesi, açılışta borsa tarafı SL+TP (algo, `closePosition`), "önce yeni sonra eski iptal" değiştirme, yedek stop, kâr kilidi ratchet, kısmi azaltma, zaman aşımı, koruma ACK zaman aşımında acil kapatma, FROZEN modu; periyodik tick olayı; net (maliyet dahil) gerçekleşmemiş PnL. Tasarım: `docs/design/faz4-cikis-kurallari.md`. Kârlılık gösterilmedi (ADR 0010).

## Faz 4 — kabul kriterleri

1. `fbot/core/position.py` saf; tüm parametreler `PositionConfig`; `null` parametre = kural kapalı.
2. Durum makinesi testleri: giriş fill → SL+TP komutları; iki ACK → MANAGED; SL tetik → TP iptal (ve tersi); koruma ACK `t_protect` içinde gelmezse reduceOnly MARKET; FROZEN'da komut yok.
3. Değiştirme sırası testi: yeni SL `v{n+1}` **önce**, eski `v{n}` iptali **sonra**; `min_replace_interval` içinde ikinci değişiklik yok; ratchet yalnızca lehte yönde.
4. R1 yedek stop, R4 kısmi azaltma (filtre altı → pas), R5 zaman aşımı (yalnızca net ≤ 0) testli.
5. `clientAlgoId`/`clientOrderId` deterministik ve ≤ 36 karakter (Binance uzunluk kuralı Faz 9'da doğrulanır).
6. Net PnL: komisyon (giriş gerçek, çıkış tahmini), funding, slippage tahmini düşülmüş; `Decimal`.
7. Engine `exec` ve `tick` olaylarını işler; replay determinizmi korunur (mevcut testler + yeni fixture ile).
8. Recorder `tick_ms` ile `ctrl/tick` üretir (replay'de aynı).
9. Replay karşılaştırması (statik SL/TP vs kurallı): basit dolum modeliyle (mark tetik, bookTicker karşı taraf) rapor; **kapı değil**, bilgilendirici (ADR 0011).

## Faz 5 — hedef ve kabul kriterleri (başlangıç 2026-09-10; tasarım `docs/design/faz5-risk-engine.md`)

Hedef: bağımsız, veto yetkili, saf Risk Engine (`assess`), kalıcı kill switch, runaway dedektörü, mutabakat kilidi. Kârlılık gösterilmedi (ADR 0010).

1. `fbot/core/risk.py` saf; K1–K18 `RiskConfig` ile; `None` = kontrol kapalı; gerekçeler katalog sırasında.
2. Çıkış niyetleri (`reduce_only`/`close_position`) K1–K11 ve K13–K16 tarafından **engellenmez**; yalnızca K12 filtre uygulanır (test).
3. Her kontrol için en az bir REJECT ve bir APPROVE testi; RESIZE (K8/K9/K14) filtre altına düşünce REJECT.
4. Kill switch: dosyada kalıcı, restart sonrası okunur, yalnızca elle sıfırlanır (`fbot/gateway/killswitch.py`, I/O kenarı; çekirdek yalnızca bayrağı okur).
5. Runaway dedektörü: kayan pencerede emir sayısı ve ardışık ret sayısı eşikleri → `KillSwitchTriggered` komutu.
6. Determinizm: aynı girdi aynı karar (test).

## Faz 5–6 teslim (2026-09-10)

| Kriter | Sonuç |
|---|---|
| Risk Engine saf, K1–K18, gerekçe sırası | `fbot/core/risk.py`, 12 test; çıkışlar yalnızca K12'den geçer |
| Kalıcı kill switch | `fbot/gateway/killswitch.py`, atomik yazım + geçmiş; restart testi |
| Mutabakat | `fbot/core/reconcile.py`: pozisyon/algo/kaldıraç/mod farkları, korumasız pozisyon listesi |
| State Engine ≡ araştırma | `tests/test_state_engine.py`: aynı bar dizisinde etiketler ve feature'lar bit-eşit |
| Decision Engine D1–D3 | `fbot/core/decision.py`, 8 test; ağırlıklı skorlama yok; sl/tp yoksa intent yok |
| Zincir | bar → durum → karar → risk → PlaceOrder; dolumda sl/tp intent yüzdesinden; 5 test |
| Determinizm | zincir iki kez oynatıldığında aynı komut dizisi |
| Toplam test | 167 |

**Yakalanan hata (2W penceresi):** durum motoru kayan pencereyi `W + N_long` bar tutuyordu; `vol_ratio` ve `spread` persentilleri W bar geçmiş isteyip kendileri de W bar pencere gerektirdiği için `pct_vol_ratio`/`pct_spread` sessizce `None` kalıyor, **S3 ve S4 hiç etiketlenmiyordu**. Pencere `2W + N_long + 2` yapıldı; aynı hata `fbot/api/live_view.py` ve `scripts/replay_positions.py` içinde de düzeltildi. Faz 5'teki "ısınma = 2W bar" kuralının kaynağı budur.

**Kârlılık gösterilmedi (ADR 0010).** `allowed_cells` boş olduğu için zincir hiçbir giriş emri üretmez; Faz 3'te maliyet üstü beklenti gösteren hücre çıkmadı.

## Faz 7/9 — boru hattı doğrulaması (2026-09-10 23:40)

Karar motoruna gözlemlenebilirlik eklenince (intent üretilmeme nedeni sayılıyor) iki gerçek engel çıktı ve düzeltildi:

| Engel | Neden | Düzeltme |
|---|---|---|
| `K9_beta_unknown` — 352 ret | `beta_cap_usdt = 750` verildi ama beta hesabı çekirdeğe bağlanmamıştı; risk fail-closed reddediyordu | `fbot/core/beta_tracker.py`: barlardan kayan BTC-beta, araştırma formülüyle bit-eşit test |
| `D3_spread` — 90 engel | demo config'deki `research_spread_bps` tahminî (DOGE 0.5 iken gerçek 1.19) | kayıttan ölçüldü (son 3 saat, bookTicker medyanı) ve üç config'e yazıldı |

Ölçülen spread (bps, medyan): BTC 0.013 · ETH 0.041 · ZEC 0.091 · HYPE 0.125 · BNB 0.14 · XRP 0.742 · SOL 1.004 · DOGE 1.192 · IOST 2.031 · VTHO 3.385

Düzeltme sonrası 3 saatlik gerçek kayıt üzerinde (demo config, strateji değil): **13 intent → 13 pozisyon → 22 dolum → 26 koruma emri**. Risk retleri artık anlamlı (`K6_max_positions`, `K8_gross_cap`, `K12_filters`), fail-closed bilinmezlik değil.

**Kârlılık gösterilmedi (ADR 0010):** hücreler ve SL/TP değerleri ölçülmemiş demo değerleridir.


## Kapanmış fazlarda açık kalan kalemler (denetim 2026-09-11)

Fazlar kapatılırken atlanan ya da sonraki faza bırakılıp orada da yapılmayan kalemler. Kapatma
kararlarını geri almıyor; ne olmadığını kayda geçiriyor.

| Faz | Açık kalem | Neden açık | Engellediği |
|---|---|---|---|
| 0 | Unit economics üç girdi (tutma süresi, işlem sayısı, hedef hareket) | Proje sahibinden gelmedi; tablo tek satıra indirgenemedi | Başabaş kazanma oranı hedefi yok |
| 0 | Komisyon kademesi doğrulanmadı | VIP0 üçüncü taraf kaynak; hesaptan teyit edilmedi | Tüm maliyet hesapları bu varsayıma dayanıyor |
| 0 | Slippage dağılımı ölçülmedi | Üç sakin anlık görüntü volatil anı temsil etmiyor; kayıt depth akışı henüz bu amaçla işlenmedi | `slippage_max_bps` config'de kapalı (K15 "ölçülmedi") |
| 3 | Canlı kayıt üzerinde ≥3 günlük nihai rapor | Karar 32 günlük arşiv verisiyle verildi (ADR 0009); kayıt 2026-09-11 20:30 itibarıyla 36 saat, üç güne 2026-09-13 08:00 UTC'de varır | Kendi verimizle doğrulama yok |
| 4 | `clientAlgoId`/`clientOrderId` uzunluğunun borsada doğrulanması | Kriter Faz 9'a bırakılmıştı; hiç emir gönderilmedi | Gerçek emirde reddedilme riski ölçülmedi |
| 5 | ~~Mutabakat süreçte çağrılmıyor~~ | **KAPANDI 2026-09-11:** `fbot/execution/exchange_state.py` borsa snapshot'ını çeker, `ReconcileSupervisor` açılışta ve 10 s'de bir karşılaştırır, farkta `state.reconciled=False` → K2 her girişi reddeder | — |
| — | Binance income kayıtlarıyla PnL mutabakatı | `TestnetClient.income()` yazıldı, hiç çağrılmıyor | **CLAUDE.md maliyet kuralı:** PnL gerçeği iç hesap değil income kayıtlarıdır |
| 2 | ~~README güncel değildi~~ | **KAPANDI 2026-09-11:** komut listesi, test sayısı ve faz durumu güncellendi | — |
| 9 | Testnet hesabında bize ait olmayan iki koruma emri | BTCUSDT, 2026-05 tarihli, `algoStatus=NEW`; mutabakat `algo_orphan` olarak işaretledi | **Testnet trading kilitli** (K2 REJECT); iptal borsada değişiklik olduğu için proje sahibi onayı bekliyor |

Açık fazlar ve bekledikleri:

| Faz | Durum | Bekleyen |
|---|---|---|
| 7 | Kâğıt işlem servisi ayakta, karar üretmiyor | Ölçülmüş giriş kuralı (`allowed_cells` boş) |
| 8 | Konsol var; metrik toplayıcı ve alarm kanalı yok | Prometheus/Grafana veya eşdeğeri; stratejiden bağımsız ilerleyebilir |
| 9 | Testnet silahlı, borsa erişimi doğrulandı, emir göndermedi | Giriş kuralı; "2 hafta hatasız" saati başlamadı |
| 10 | Bekliyor | Faz 9 sonucu ve proje sahibi onayı; `LiveExecutionAdapter` korumalı stub |
