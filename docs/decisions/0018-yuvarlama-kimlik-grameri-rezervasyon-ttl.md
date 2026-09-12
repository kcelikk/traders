# ADR 0018 — Filtre tabanlı yuvarlama, kimlik grameri ve giriş rezervasyonu TTL'i (Gate 2.0)

Tarih: 2026-09-12 · Durum: kabul edildi · Kapsam: Gate 2.0 · **Planlı re-baseline #1**

## Bağlam

Gate 0'ın testnet doğrulaması (`docs/binance-api-gate0-dogrulama.md`) ve kod taraması dört doğruluk
hatası çıkardı. Hepsi `allowed_cells` boş olduğu için bugün tetiklenmiyor; strateji açıldığı anda
gerçek para riskine dönüşürler.

1. **Tetik fiyatı tick'e oturmuyor.** `_entry_from_meta` yüzdelerden türetilen `sl`/`tp`'yi
   yuvarlamadan geçiriyordu: `97.51995` gibi bir tetik, `tick_size = 0.01` olan bir sembole
   gidiyordu. Borsa tetik alanında tickSize'ı **zorlamıyor** (Gate 0 §4 ile doğrulandı, önceki
   iddia yanlıştı), yani emir reddedilmiyor — ama koruma fiyatı ile defter arasında sistematik
   sapma kalıyor ve fiyat hiçbir gerçek seviyeye denk gelmiyor.
2. **Precision, tick'in yerine kullanılıyordu.** `testnet_adapter._fmt` `pricePrecision` ile
   `ROUND_HALF_EVEN` yapıyordu. BTCUSDT testnet'te `tickSize=0.10` · `pricePrecision=2`; ikisi
   uyuşmuyor, precision'a yuvarlamak tick'e oturmayan fiyat üretiyor. Miktarın yarım-yukarı
   yuvarlanması ayrıca bakiyeyi aşabilir.
3. **`clientAlgoId` 36 karakteri aşabiliyordu.** `pos_id` zaten 36'ya kırpılmışken `-SL-v1`
   eklenince 42 karakter oluyor → `-4015`. Yani koruma emri hiç konulamıyor. Fiili sınır 36
   **dahil** (Gate 0 §3).
4. **`pending_entries` sızıntısı.** Tek silme noktası vardı (`entry_fill`). Emir reddedilirse ya da
   sonucu bilinmezse sembol sonsuza kadar rezerve kalıyor, K5 o sembolde bir daha giriş üretmiyordu.

## Karar

### 1. `fbot/core/rounding.py` — tek yuvarlama noktası

`floor_step`, `round_tick`, `trigger_price`, `fmt_qty`, `fmt_price`. Kaynak **`Filters`**
(`step_size`, `tick_size`); `pricePrecision` hiçbir yerde kullanılmaz.

Miktar her zaman aşağı. Tetik fiyatı **piyasadan uzağa**:

| | tetik nerede | yön |
|---|---|---|
| long SL | piyasanın altında | aşağı |
| long TP | piyasanın üstünde | yukarı |
| short SL | piyasanın üstünde | yukarı |
| short TP | piyasanın altında | aşağı |

Gerekçe validite: yanlış yöne yuvarlamak tetiği piyasanın öbür tarafına geçirebilir (anında
tetiklenen emir, `-2021`). Tick boyutları küçük olduğu için PnL etkisi ihmal edilebilir.

`fmt_price` tick'e oturmayan fiyatı **reddeder**, sessizce yuvarlamaz: yuvarlama çekirdeğin işidir,
I/O kenarının değil. Sembolün filtresi yoksa `MissingFilters` → emir gönderilmez (fail-closed).

### 2. `fbot/core/ids.py` — kimlik grameri

```
pos_id = {tag}{L|S}{10 hex}        f0Ledd0ff2338      (≤ 15)
algo   = {pos_id}-{SL|TP}-v{n}     f0Ledd0ff2338-SL-v1 (≤ 23)
çıkış  = {pos_id}-{X|TP1}-v{n}
```

Uzunluk **girdiden bağımsız**: sembol adı ve zaman damgası hash'e girer, kimliğe değil.
`check()` her üretim noktasında `len ≤ 36` doğrular.

Plandaki `{tag}{role}{hash}` biçiminden sapma: ayraç korunur. Sebep, simülatörün ve trader'ın exec
olayında `pos_id`'yi önekten çözmesi (`pos_id_of`); saf hash grameri ya bu eşlemeyi kırar ya da
I/O kenarına bir kayıt defteri ekler. Gate 3'ün sahipsiz emir temizliği de "bizim gramerimize
uyanlar" ayrımını buradan yapacak.

`strategy_tag` config'ten gelir ve ortam başına farklıdır (`p0` paper, `t0` testnet, `d0` demo):
aynı borsa hesabında iki ortam birbirinin emrini sahiplenemez.

### 3. `pending_entries`: `set` → `dict[symbol] = deadline_ns`

Tick'te TTL süpürmesi; `order_rejected` / `order_unknown` olayında anında bırakma. TTL config'ten
(`[core] pending_entry_ttl_ms`, bugün 60 s).

`order_unknown`ta emir gerçekleşmiş olabilir. Rezervasyonu tutmak sızıntıdır, bırakmak tek başına
güvenli değildir; güvenlik mutabakattadır: `needs_reconcile` K2 kilidini çalıştırır.

## Re-baseline #1 — komut düzeyi fark tablosu

`tests/golden/replay_baseline.json` (rec-mini) **değişmedi**: o fixture'da strateji kapalı, yalnız
`BarClosed` üretiliyor. Yani emir alanlarındaki hiçbir regresyon o baseline'ı kırmıyordu. Bu boşluk
Gate 2.0'da `tests/golden/orders_baseline.json` ile kapatıldı: senaryo
`tests/scenario.py::live_run(discovered_cells())`, 140 komutun her alanı dosyada.

`make golden-orders-diff` çıktısı:

| alan | değişen komut | örnek (eski → yeni) |
|---|---|---|
| `PlaceAlgo.client_algo_id` | 55 | `eXUSDT899999L-SL-v1` → `f0Ledd0ff2338-SL-v1` |
| `PlaceAlgo.trigger_price` | 38 | `97.51995` → `97.51` |
| `CancelAlgo.client_algo_id` | 36 | `eXUSDT899999L-SL-v1` → `f0Ledd0ff2338-SL-v1` |
| `PlaceOrder.client_id` | 19 | `eXUSDT899999L` → `f0Ledd0ff2338` |

Komut sayısı (140) ve tür dağılımı (`PlaceAlgo` 55, `CancelAlgo` 36, `PlaceOrder` 19,
`StateChanged` 30) **değişmedi**. Başka hiçbir alanda fark yok — planın kapı koşulu buydu.
55 tetikten 38'i değişti; kalan 17'si zaten tick'e oturuyordu.

## Sonuçlar

- Golden `rec-mini` hash'i korundu; `make test-determinism` artık emir baseline'ını da koşuyor.
- `Engine.step` p50/p99 değişmedi (7,06 / 15,79 µs; baseline 6,9 / 15,1).
- `TestnetAdapter.symbols` artık `Filters` taşıyor; `pricePrecision` kullanılmıyor.
- Kimlikler okunabilirliğini yitirdi (hash). Sembol ve zaman `entry_meta` ile `orders` tablosunda
  duruyor; konsol atfı oradan yapar.
- Testler: 495 → 527.
