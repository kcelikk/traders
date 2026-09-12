# Gate 0 — Binance testnet davranış doğrulaması

Tarih: 2026-09-12 · Ortam: **testnet** (`testnet.binancefuture.com`) · Sembol: BTCUSDT
Betik: `scripts/verify_exchange_behavior.py` (elle çalıştırılır, üretim yoluna bağlı değildir)

Bu belge dokümantasyondan varsayım içermez. Her satır gerçek bir istek ve gerçek bir cevaptır.
Her koşu sonunda açık emir, açık algo ve açık pozisyon sıfır olduğu doğrulanmıştır.

---

## 1. Private WebSocket URL biçimi

| Denenen | Sonuç |
|---|---|
| `wss://stream.binancefuture.com/ws/<listenKey>` | **ÇALIŞTI** |
| `wss://stream.binancefuture.com/private/ws?listenKey=...` | denenmedi (ilki çalıştı) |

`listenKey` uzunluğu 64 karakter. Testnet stream tabanı `stream.binancefuture.com`, REST tabanından
(`testnet.binancefuture.com`) farklıdır.

**Not:** Mainnet'te `/public` `/market` `/private` ayrımı dokümanda belirtilmiştir
(`docs/binance-api-verification.md` §1). Testnet'te çalışan biçim klasik `/ws/<listenKey>` yoludur.
Mainnet private URL biçimi **ayrıca doğrulanmalıdır**; testnet sonucu mainnet için kanıt değildir.

## 2. Private olay payload'ları (yakalandı)

Bir market emri açılıp koruma emri konup iptal edilirken dinlendi.

### `TRADE_LITE` — **dokümanda yoktu, kodda hiç yok**

```json
{"e":"TRADE_LITE","E":...,"T":...,"s":"BTCUSDT","q":"0.0007","p":"0.00","m":false,
 "c":"<clientOrderId>","S":"BUY","L":"77290.70","l":"0.0007","t":536962673,"i":28581489905}
```

`ORDER_TRADE_UPDATE`'ten **önce** gelen hafif dolum bildirimi. `fbot/gateway/userdata_map.py`
bu tipi tanımıyor; `map_user_event` `None` döndürür. Yok saymak güvenlidir (aynı bilgi
`ORDER_TRADE_UPDATE`'te var) ama bilinçli bir karar olmalı.

### `ORDER_TRADE_UPDATE` — alanlar doğrulandı

`o` içinde: `s, c, S, o, f, q, p, ap, sp, x, X, i, l, z, L, n, N, T, t, b, a, m, R, wt, ot, ps,
cp, rp, pP, si, ss, V, pm, gtd, er`

Kritik olanlar: `t` = tradeId (dedupe için, **bugün `map_user_event` bunu okumuyor**),
`i` = orderId, `n` = komisyon, `N` = komisyon varlığı, `rp` = gerçekleşen PnL, `z` = kümülatif
miktar, `ps` = `"BOTH"` (ONE-WAY), `V` = `"EXPIRE_MAKER"` (STP modu), `wt` = `"CONTRACT_PRICE"`
(market emirde).

Örnek dolum: `"x":"TRADE","X":"FILLED","l":"0.0007","z":"0.0007","L":"77290.7","n":"0.02164139","N":"USDT"`

### `ACCOUNT_UPDATE` — alanlar doğrulandı (daha önce doğrulanmamıştı)

```json
{"e":"ACCOUNT_UPDATE","T":...,"E":...,
 "a":{"B":[{"a":"USDT","wb":"4208.43752587","cw":"4208.43752587","bc":"0"}],
      "P":[{"s":"BTCUSDT","pa":"0.0007","ep":"77290.7","cr":"-61.78","up":"-0.008",
            "mt":"cross","iw":"0","ps":"BOTH","ma":"USDT","bep":"77321.61628"}],
      "m":"ORDER"}}
```

`a.P[].pa` işaretli pozisyon miktarı, `ep` giriş fiyatı, `bep` başabaş fiyatı, `a.m` tetikleyen neden.

### `ALGO_UPDATE` — alanlar doğrulandı, **bir alan dokümanda yoktu**

```json
{"e":"ALGO_UPDATE","T":...,"E":...,
 "o":{"caid":"...","aid":1000000202490585,"at":"CONDITIONAL","o":"STOP_MARKET","s":"BTCUSDT",
      "S":"SELL","ps":"BOTH","f":"GTE_GTC","q":"0","X":"NEW","ai":"","tp":"74960.75","p":"0",
      "V":"EXPIRE_MAKER","wt":"MARK_PRICE","pm":"NONE","cp":true,"pP":true,"R":true,"tt":0,
      "gtd":0,"ia":false}}
```

`f` = `"GTE_GTC"` — koruma emrinin time-in-force'u. `docs/binance-api-verification.md` §12'deki
alan listesinde yoktu. `-4130` hatasının metnindeki "GTE" buna atıftır.

### `listenKeyExpired`

Bu koşuda görülmedi (oturum 60 dakikadan kısaydı). **Hâlâ doğrulanmadı.**

## 3. `clientOrderId` uzunluk sınırı

| Uzunluk | Sonuç |
|---|---|
| 35 | KABUL |
| 36 | **KABUL** |
| 40 | RET, `-4015` "Client order id length should be less than 36 chars" |

Hata metni "36'dan az" diyor ama 36 karakter kabul ediliyor. **Fiili sınır 36 dahil.**
`fbot/core/decision.py:95` `cid[:36]` bu yüzden doğru.

**Ama `clientAlgoId` kırpılmıyor**: `fbot/core/position.py:89-94` `f"{pos_id}-SL-v{n}"` üretiyor ve
`pos_id` zaten 36'ya kırpılmış olabiliyor → 42 karakter → `-4015`. Bu **gerçek bir hata**, Gate 2.0.

## 4. tickSize zorlaması — **önceki iddiam yanlıştı, düzeltiyorum**

BTCUSDT testnet: `tickSize = 0.10`, `pricePrecision = 2` → ikisi uyuşmuyor (mainnet'te de öyle).

Tetik fiyatı `74960.75` (0,10'un katı **değil**) ile koruma emri gönderildi: **KABUL EDİLDİ**.
`ALGO_UPDATE` içinde `"tp":"74960.75"` olarak göründü.

**Sonuç: Binance algo `triggerPrice` alanında tickSize'ı zorlamıyor.** Dolayısıyla
"BTCUSDT'de ilk koruma emri geçersiz fiyatla reddedilir" iddiam **doğru değildi**. Tick'e
yuvarlama hâlâ doğru davranıştır (tetik gerçek bir fiyat seviyesine denk gelsin diye) ama
**canlı bir kırılma değildir**; Gate 2.0'daki önceliği buna göre düşer.

LIMIT emir `price` alanında tickSize zorlaması **denenmedi** (üretilen tüm emirler MARKET).

## 5. Aynı `clientOrderId` ile ikinci gönderim

Aynı `newClientOrderId` ile iki MARKET emri arka arkaya gönderildi. **İkisi de kabul edildi**,
farklı `orderId` döndü (28581489084 ve 28581489089) ve **ikisi de doldu** (pozisyon 2 × miktar).

**Sonuç: duplicate `clientOrderId` reddi idempotency garantisi değildir.** Dedupe borsanın
reddine dayanamaz; yerel intent kayıt defteri zorunludur. Bu, planın §6 gereksinimini doğruluyor.

## 6. `-2022` ReduceOnly reddi

Pozisyon kapalıyken `reduceOnly=true` MARKET emri → `-2022 "ReduceOnly Order is rejected."`

Bu kod tek başına "pozisyon zaten kapalı" anlamına gelmez; başka nedenlerle de gelebilir.
`fbot/gateway/testnet.py:23` `EXPECTED_CODES` içinde ve sessizce yutuluyor. ADR ile
UNKNOWN sınıfına alınacak (plan §3d).

## 7. **`-4130`: aynı yönde ikinci `closePosition` koruma emri konamıyor**

En önemli bulgu.

| Deneme | Sonuç |
|---|---|
| Pozisyon açıkken 1. `STOP_MARKET closePosition=true` | KABUL |
| Eskisi dururken 2. `STOP_MARKET closePosition=true` (farklı CID, farklı tetik) | **RET `-4130`** |
| `STOP_MARKET` dururken `TAKE_PROFIT_MARKET closePosition=true` | KABUL |

Hata metni: *"An open stop or take profit order with GTE and closePosition in the direction is existing."*

### Bunun anlamı: R3 trailing kuralı gerçek borsada korumayı kaldırır

`fbot/core/position.py:223` şu sırayı üretiyor:

```python
cmds += [self._algo(pos, "STOP_MARKET", desired, pos.sl_id), CancelAlgo(pos.symbol, old_id)]
```

Yani **önce yeni SL, sonra eskisinin iptali**. `docs/design/faz4-cikis-kurallari.md` bunu yarış
durumuna karşı doğru sıra olarak tanımlıyor. Gerçek borsada olacak olan:

1. Yeni SL → `-4130` ile **reddedilir**.
2. `-4130` `EXPECTED_CODES` içinde **değil** → `TestnetAdapter._error_event` istisnayı yükseltir →
   `TestnetTrader._send` yakalar, `order_failed` olayı yazar ve döner.
3. Döngüdeki bir sonraki komut `CancelAlgo` bağımsız olarak işlenir ve **başarılı olur**.
4. Sonuç: **pozisyon stop'suz kalır.** Çekirdek ise `pos.sl_price`'ı yeni değere güncellemiş,
   `active_algos`'a yeni id'yi eklemiş durumdadır — iç durum ile borsa birbirini tutmaz.

Trailing kuralı, korumayı sıkılaştırmak yerine **tamamen kaldırır**. Bu kural
`config/testnet.toml:63` içinde `lock_trigger_pct = "0.30"` ile **açıktır**.

Şu an tetiklenmiyor çünkü `allowed_cells` boş, yani hiç pozisyon açılmıyor. Strateji tanımlandığı
anda canlı bir güvenlik açığına dönüşür.

### Seçenekler (Gate 3'te karar verilecek, ADR gerekir)

1. **Sırayı ters çevir**: önce iptal, sonra yeni SL. Kısa korumasız pencere (~1 RTT) doğar.
2. **`closePosition=false` + açık miktar** kullan: birden çok stop'a izin veriliyor mu, ölçülmeli.
3. **Yedek katman**: R1 uygulama tarafı yedek stop zaten var; korumasız pencere boyunca o devrede.

Seçenek 1 + 3 birlikte en muhafazakâr görünüyor, ama önce seçenek 2 ölçülmeli.

---

## Bu koşuların hesap üzerindeki izi

Her koşu sonunda `openOrders`, `openAlgoOrders` ve açık pozisyon **sıfır** doğrulandı.
Bir koşu `-4130` nedeniyle ortada kesildi ve bir algo ile bir pozisyon bıraktı; elle temizlendi
ve sonuç doğrulandı (algo 0, emir 0, pozisyon 0).
