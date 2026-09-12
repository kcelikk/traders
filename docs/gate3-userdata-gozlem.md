# Gate 3b — private akış shadow gözlemi

Tarih: 2026-09-12 · Ortam: **canlı `fbot-testnet` servisi** (ayrı kurulum yapılmadı) · commit `45f1500`

Gözlem, çalışan servisin kendi private bağlantısıyla yapılıyor. Amaç, çekirdek hiçbir şey
tüketmeden gerçek veriyi toplayıp kayıt üzerinden doğrulamak.

## 1. Bağlantı kuruldu

`stream_base = wss://stream.binancefuture.com` + `/ws/<listenKey>` (Gate 0 §1 ile doğrulanmış biçim).

| Ölçüt | Değer |
|---|---|
| alınan listenKey | 1 |
| bağlantı | kuruldu, kopma yok |
| mod | `shadow` (çekirdek tüketmiyor) |
| sahipsiz emir temizliği | `dry_run` |

listenKey ctrl olayına, log'a ve kayda **maskeli** giriyor (`…VjI6` biçiminde); tam anahtar hiçbir
yere yazılmıyor.

## 2. Çerçeve teslimi kanıtlandı

`scripts/probe_userdata.py`: piyasanın **%50 altında** bir LIMIT BUY (dolması mümkün değil),
3 saniye sonra iptal. Pozisyon açılmadı, market emri gönderilmedi, koşu sonunda açık emir 0 ve açık
pozisyon 0 doğrulandı.

```
mark 77319.90 · limit 38659.90 · qty 0.002 · cid probe1789207201232
placed  → orderId 28581566540 status NEW
canceled → status CANCELED
temiz: open_orders 0 · open_positions 0
```

Kayda düşen çerçeveler (`c":"private"`, tek sıralama noktasından geçmiş):

| # | tip | `x` / `X` | sonuç |
|---|---|---|---|
| 1 | `ORDER_TRADE_UPDATE` | `NEW` / `NEW` | `order_ack` olarak eşlendi |
| 2 | `ORDER_TRADE_UPDATE` | `CANCELED` / `CANCELED` | `order_done` olarak eşlendi |

**Teslim gecikmesi** (borsa olay damgası `T` → bizim `recv_ns`): 140,4 ms (n=2). Bu, Gate 3'ün
"fill → çekirdek gecikmesi" ölçümünün ilk değeridir; dolum çerçevesiyle tekrar ölçülecek.

## 3. Eşleyicide kapatılan gerçek hata

`scripts/verify_userdata.py` kayıt üzerinden eşleyiciyi koşturdu ve iki alanın **okunmadığını**
gösterdi:

| alan | durum |
|---|---|
| `o.t` (tradeId) | okunmuyordu → `OrderBook.apply` dedupe için bunu arıyor, bulamadığı için **tekrar bastırma sessizce çalışmıyordu** |
| `o.i` (orderId) | okunmuyordu |

İkisi de eklendi ve testle kilitlendi (aynı `tradeId` ikinci kez gelince `dup_trades` artıyor,
dolum miktarı iki katına çıkmıyor). `t = 0` gelen çerçevede `trade_id` `None` kalır: sıfır bir
tradeId değildir.

Ayrıca Gate 0 §2'de payload'ı yakalanmış olan üç tip eşleyiciye eklendi: `TRADE_LITE` (dokümanda
yok, `ORDER_TRADE_UPDATE`'ten önce gelir — çift sayılmaması için kendi kindi var),
`ACCOUNT_UPDATE`, `ACCOUNT_CONFIG_UPDATE` ve `MARGIN_CALL`. Bu üçünün alanları **Gate 0'da gerçek
testnet çerçevelerinden** alındı, uydurulmadı; ama bu gözlem koşusunda görülmediler (dolum yok).

## 4. Sahipsiz koruma emri — dry-run

Kural: **yalnız bizim kimlik gramerimize uyan** algo iptal edilir
(`{tag}{L|S}{hash}-{SL|TP}-v{n}`, `fbot/core/ids.py`). Uymayanlar `foreign_untouched` listesinde
raporlanır ve **dokunulmaz**; etiket verilmezse hiçbir iptal üretilmez (fail-closed).

İlk mutabakatın çıktısı:

```
reconciled true · mismatches [] · orphan_cancel {mode: dry_run, planned: [], applied: [],
                                                foreign_untouched: []}
```

`docs/PHASE.md` denetim tablosunda kayıtlı iki sahipsiz koruma emri **artık hesapta yok**; bu koşuda
sahipsiz algo görülmedi. Kural bu yüzden canlı veriyle değil, birim testleriyle doğrulandı
(`tests/test_orphan_cancel.py`: bizim emrimiz plana girer, yabancı emir girmez, `apply` modunda
yalnız bizimki iptal edilir, iptal hatası yutulmaz).

## 5. Hâlâ doğrulanmayanlar (gözlem sürüyor)

| Konu | Neden bugün doğrulanamadı | Ne zaman |
|---|---|---|
| `listenKeyExpired` | key ömrü 60 dk; keepalive çalıştığı sürece hiç görülmez | keepalive kasıtlı durdurulursa ya da uzun gözlemde |
| keepalive başarı oranı | ilk keepalive ~30 dk sonra | servis 30 dk çalıştıktan sonra |
| `TRADE_LITE`, `ACCOUNT_UPDATE`, dolum çerçevesi | gerçek dolum gerekir; sonda pozisyon bırakır | Gate 3c doğrulama koşusunda (onay gerekir) |
| `order_fill` → çekirdek gecikmesi | dolum yok | aynı koşu |
| dup `tradeId` sayısı | dolum yok | aynı koşu |

## BU ADIMDA YAPILMAYANLAR

- **Çekirdek user data tüketmiyor.** `OrderRegistry` (`cid → pos_id`), `exit_in_flight`,
  `UNKNOWN` durumu ve `-2022` politikası Gate 3c/3d işidir; shadow adımının amacı buydu.
- `unprotected` onarımı (koruma yeniden koyma) yazılmadı.
- Balance/margin snapshot'a eklenmedi; HEDGE'te ARM reddi hâlâ yok.
- `income()` çağrılmıyor: gerçek komisyon ve funding iç muhasebeye aktarılmıyor (Gate 4).
- Paper servisinde user data kapalı (`enabled = false`); orada borsa hesabı yok.
