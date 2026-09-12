# ADR 0019 — Bloklamayan emir yolu: kalıcı bağlantı, gönderim kuyruğu, sınıf bazlı rezerv (Gate 2.1)

Tarih: 2026-09-12 · Durum: kabul edildi · Kapsam: Gate 2.1 · **hash-nötr**

## Bağlam

Gate 1 ölçümü (`docs/gate1-olcum.md` §6) `fbot-testnet`'te loop lag en kötü p99'unu **3.214 ms**
olarak raporladı ve kaynağını kalıcılık dışında bir yere işaret etti. Kaynak şuydu: emir gönderimi
ve periyodik borsa sorguları (silahlanma denetimi, mutabakat) senkron `http.client` çağrılarıydı ve
**olay döngüsünün içinde** çalışıyordu. Her çağrı ayrıca yeni bir TLS el sıkışması ödüyordu
(`fbot/gateway/testnet.py:_http` her istekte yeni `HTTPSConnection` açıyor).

İkinci boşluk: taşıma katmanı hataları hiç yakalanmıyordu. `socket.timeout` çağrı zincirinde yukarı
çıkıyor ve emir "gönderilmedi" sayılıyordu. Oysa POST'ta zaman aşımı **yürütme durumu bilinmiyor**
demektir; Gate 0 §5 aynı `clientOrderId` ile ikinci gönderimin reddedilmediğini, iki emrin de
dolduğunu gösterdi — yani kör retry iki pozisyon açar.

ADR 0002 ek HTTP kütüphanesi yasaklıyor; `aiohttp` hem yeni bağımlılık hem ADR ihlali olurdu.

## Karar

### 1. `fbot/gateway/http_pool.py` — kalıcı bağlantı havuzu (stdlib)

Tek host, tek kalıcı bağlantı, kilit altında sıralı kullanım. Ayrı **bağlanma** ve **okuma**
bütçesi: tek `timeout` ile bağlantı kurulamadığı hâlde 10 s beklenebiliyordu. Boşta kalan bağlantı
`max_idle_s` sonunda düşürülür; sunucu `Connection: close` derse kapatılır.

**Kör retry yok.** `GET` yalnızca **yeniden kullanılmış** bir bağlantı koptuğunda bir kez
tekrarlanır (sunucunun keep-alive'ı kapatma biçimi budur). `POST` ve `DELETE` asla tekrarlanmaz.

### 2. `fbot/execution/queue.py` — sınırlı gönderim kuyruğu, sınıf bazlı rezerv

Komut kuyruğa alınır; tek işçi FIFO boşaltır ve HTTP'yi `asyncio.to_thread` ile yapar. Sonuç tek
sıralama noktasından (`Recorder.emit`) `exec` olayı olarak akışa yazılır; replay'de bu olaylar
kayıttan okunur, yeniden çalıştırılmaz — Rule Zero korunur.

Sıkışıklıkta önce **giriş** emirleri reddedilir; koruma (`PlaceAlgo`/`CancelAlgo`/`CancelOrder`) ve
çıkış (`reduceOnly`) için ayrılmış slot her zaman durur. Pozisyonu kapatamamak, açamamaktan
pahalıdır. Bu `RateLimiter.reserve_orders` kuralının kuyruk karşılığıdır. Rezerv bir **kabul**
kuralıdır, sıra değiştirme değil: FIFO bozulmaz. Reddedilen komut `ctrl/order_dropped` olayı olur
ve sayılır; sessiz düşme yok.

### 3. Taşıma hatalarının sınıflandırılması

`TestnetClient._call`: zaman aşımı / bağlantı kopması / ağ hatası → `TestnetError`. `POST` ve
`DELETE` için `unknown_execution=True` (adapter bunu `order_unknown` + `needs_reconcile` olayına
çevirir, mutabakat K2 kilidini işletir); `GET` için `False` — okuma hiçbir şey yürütmez, gereksiz
mutabakat kilidi üretmemeli.

### 4. 429'da `Retry-After`

`RateLimiter.on_response` artık başlıkları okur. Sabit 10 s beklemek, borsa 60 s dediğinde yeni bir
429 üretiyordu. 418'de ban **ve** geri çekilme birlikte işlenir; ban elle sıfırlanana kadar açılmaz
(kill switch bağlantısı Gate 4).

### 5. Periyodik borsa sorguları döngüden çıktı

`PaperRecorder.paper_status_task` artık `_pre_beat()` kancasını `await` ediyor; `TestnetRecorder`
silahlanma denetimini ve mutabakatı `asyncio.to_thread` ile çalıştırıyor. Sonuçların akışa yazımı
yine döngü thread'inde — tek sıralama noktası korunuyor.

### 6. Geri alma: `[execution] transport = "legacy"`

Varsayılan `legacy`; yalnız `config/testnet.toml` `persistent_async` diyor. Legacy yolda gönderim
eski davranışı (olay yolunda senkron) korur ve iki yol da aynı testlerden geçer.

## Ölçüm

`scripts/bench_transport.py`, imzalı okuma (`/fapi/v2/balance`), gerçek testnet, n=50:

| | p50 | p95 | p99 | min | TLS el sıkışması |
|---|---|---|---|---|---|
| legacy (istek başına bağlantı) | 367,6 ms | 448,5 ms | 768,0 ms | 353,2 ms | 50 |
| kalıcı havuz | **270,5 ms** | 736,9 ms | 739,1 ms | **264,1 ms** | **1** |

p50'de 97 ms (%26) kazanç ve el sıkışma sayısı 50 → 1. Kuyruk taban çizgisi p95/p99'da iki yol da
~740 ms'lik sunucu kaynaklı diken görüyor; bu fark ölçüm gürültüsüdür, iki koşuda da tekrarlandı.

## Sonuçlar ve sınırlar

- Golden hash değişmedi; gate hash-nötr. 556 test.
- **Emir POST'unun RTT'si ayrıca ölçülmedi.** `allowed_cells` boş olduğu için canlı emir akışı yok;
  ölçüm imzalı okuma üzerinden yapıldı. Aynı TLS ve imza yolunu kullanır ama emir uç noktasının
  sunucu tarafı gecikmesi farklı olabilir.
- **Canlı loop lag iyileşmesi henüz ölçülmedi**: dikenin kaynağı olan periyodik sorgular thread'e
  taşındı, kazancı bir sonraki gözlem penceresinde raporlanacak.
- Kuyruk derinliği ve reddedilen giriş sayısı bugün sıfır kalacak (emir üretilmiyor); sayaçlar
  `paper_stats.execution` ve canlılık damgasında yayında.
- `income()` çağrısı, listenKey keepalive ve user data akışı hâlâ bağlı değil — Gate 3.
