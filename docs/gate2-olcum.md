# Gate 2 ölçümü — doğruluk düzeltmeleri ve bloklamayan emir yolu

Tarih: 2026-09-12 · Commit `8530bfb` (2.0), `6d10cdb` + `34d2c7b` (2.1) · ADR 0018, ADR 0019

## 1. Kapılar

| Kapı | Sonuç |
|---|---|
| `make test` | 495 → **557 geçti** |
| `make test-determinism` (saflık + iki process + iki golden) | yeşil |
| `tests/golden/replay_baseline.json` (rec-mini) | **değişmedi** |
| `tests/golden/orders_baseline.json` | **bilerek yenilendi** (re-baseline #1) |
| `make bench-guard` | yeşil |
| `Engine.step` p50 / p99 | 6,90 / 16,92 µs (baseline 6,9 / 15,1) — fark gürültü içinde |

## 2. Re-baseline #1 — komut düzeyi fark

`make golden-orders-diff`. Senaryo `tests/scenario.py::live_run(discovered_cells())`, 140 komut.

| alan | değişen komut | örnek |
|---|---|---|
| `PlaceAlgo.client_algo_id` | 55 | `eXUSDT899999L-SL-v1` → `f0Ledd0ff2338-SL-v1` |
| `PlaceAlgo.trigger_price` | 38 | `97.51995` → `97.51` |
| `CancelAlgo.client_algo_id` | 36 | aynı gramer değişimi |
| `PlaceOrder.client_id` | 19 | `eXUSDT899999L` → `f0Ledd0ff2338` |

Komut sayısı ve tür dağılımı değişmedi; başka hiçbir alanda fark yok. Planın kapı koşulu buydu.
55 tetikten 38'i değişti — kalan 17'si zaten tick'e oturuyordu.

**Ölçülen boşluk:** `rec-mini` baseline'ı yalnız `BarClosed` içeriyor (o fixture'da strateji kapalı),
yani emir alanlarındaki hiçbir regresyonu yakalamıyordu. Emir düzeyi baseline bu yüzden eklendi.

## 3. Transport RTT'si — legacy vs kalıcı bağlantı

`make bench-transport N=50`, gerçek testnet, imzalı **okuma** (`/fapi/v2/balance`). Emir gönderilmedi.

| | p50 | p95 | p99 | min | TLS el sıkışması |
|---|---|---|---|---|---|
| legacy (istek başına bağlantı) | 367,6 ms | 448,5 ms | 768,0 ms | 353,2 ms | 50 |
| kalıcı havuz | **270,5 ms** | 736,9 ms | 739,1 ms | **264,1 ms** | **1** |

p50'de 97 ms (%26) kazanç. p95/p99'daki ~740 ms diken iki yolda da görülüyor ve sunucu
kaynaklıdır; iki ayrı koşuda tekrarlandı (n=30 ve n=50).

**Canlı doğrulama** (`fbot-testnet`, dağıtımdan 10 dk sonra, canlılık damgası):

```
pool: requests 185 · connects 1 · reused 184 · retries 0 · timeouts 0 · errors 0
```

Yani 185 istek için 185 değil **1** TLS el sıkışması.

## 4. Loop lag — Gate 1'in açık bulgusu kapandı

Gate 1 ölçümü `fbot-testnet`'te en kötü p99'u 3.252 ms olarak raporlamış ve kaynağını olay
döngüsündeki senkron REST çağrılarına bağlamıştı. Gate 2.1'de emir gönderimi kuyruğa, periyodik
silahlanma denetimi ve mutabakat `asyncio.to_thread`'e taşındı.

| `fbot-testnet` loop lag | Gate 1 (öncesi) | Gate 2 (sonrası) |
|---|---|---|
| p50 (medyan) | 0,70 ms | 0,67 ms |
| p99 (medyan) | 2,16 ms | 2,02 ms |
| **p99 (en kötü)** | **3.252 ms** | **7,7 ms** |
| **maks** | **4.330 ms** | **38,4 ms** |

Pencere: 9,4 dakika, 55 istatistik örneği, 274,9 olay/s. Diken üç mertebe küçüldü; kalan 38 ms'lik
tepe tek seferlik ve 1 ms bütçesinin üstünde ama alarm eşiğine yakın değil.

## BU ÖLÇÜMDE YAPILMAYANLAR

- **Emir POST'unun RTT'si ayrıca ölçülmedi.** `allowed_cells` boş, canlı emir akışı yok; ölçüm
  imzalı okuma üzerinden yapıldı. Aynı TLS ve imza yolunu kullanır, ama emir uç noktasının sunucu
  tarafı gecikmesi farklı olabilir. Gerçek emirle ölçüm `make verify-exchange` ile yapılabilir ve
  proje sahibi onayı gerektirir.
- **Kuyruk derinliği ve reddedilen giriş sayısı sıfır** (emir üretilmiyor). Sınıf bazlı rezervin
  canlı davranışı ancak strateji açılınca ölçülür; bugün yalnız testlerle doğrulandı.
- **Yuvarlama düzeltmesinin PnL etkisi ölçülmedi**; tick boyutları küçük, etkisi validite
  tarafındadır (yanlış yöne yuvarlama `-2021` üretebilir).
- `income()`, listenKey keepalive ve user data akışı hâlâ bağlı değil — Gate 3.
- `fbot-paper` legacy transport'ta kaldı (simülatör kullanıyor, gerçek HTTP emri yok).
