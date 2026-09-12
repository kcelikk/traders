# Mainnet doğrulaması

Tarih: 2026-09-12 · Kaynak: `fapi.binance.com`, **imzasız uçlar** · Betik: `scripts/verify_mainnet_public.py`
Ham çıktı: `docs/mainnet-public.json`

Testnet sonucu mainnet için kanıt değildir (Gate 0 §1). Bu belge, mainnet'te **anahtar
gerektirmeden** doğrulanabilen her şeyi ölçer. Emir gönderilmedi, para riski yok.

## 1. Ölçülen hata: rate limit değeri ortama göre değişiyor

| Limit | Kodda sabitti | Mainnet (ölçülen) | Testnet |
|---|---|---|---|
| `REQUEST_WEIGHT` / dk | 6000 | **2400** | 6000 |
| `ORDERS` / 10 s | 300 | 300 | 300 |
| `ORDERS` / dk | 1200 | 1200 | 1200 |

`fbot/gateway/testnet.py` ağırlık limitini **6000 olarak sabitliyordu**; bu değer testnet
`exchangeInfo`'sundan alınmıştı. Mainnet'te gerçek limit 2400, yani sistem kendini **2,5 kat fazla
bütçesi var** sanacaktı. Kullanılan ağırlık cevap header'larından senkronlandığı için sayaç doğru
kalıyordu, ama **kalan** yanlış hesaplanıyordu.

**Düzeltildi:** limitler artık `exchangeInfo`'dan okunuyor
(`fbot/core/rate_limit.py:limits_from_exchange_info`). Borsa bir limiti söylemezse muhafazakâr
değer kullanılır (2400/300/1200): söylenmemiş bir limiti yukarı yuvarlamak 429 üretmenin en kısa
yoludur.

## 2. Yuvarlama kararı mainnet'te de doğrulandı

ADR 0018'in gerekçesi `tickSize` ile `pricePrecision`'ın uyuşmamasıydı. Mainnet'te:

| Sembol | tickSize | pricePrecision | uyuşuyor mu | stepSize | minNotional |
|---|---|---|---|---|---|
| BTCUSDT | 0,10 | 2 | **hayır** | 0,001 | 50 |
| ETHUSDT | 0,01 | 2 | evet | 0,001 | 20 |
| SOLUSDT | 0,0100 | 4 | **hayır** | 0,01 | 5 |

İki sembolde uyuşmazlık var ve yönleri farklı: BTCUSDT'de tick precision'dan **kaba**, SOLUSDT'de
**ince**. `pricePrecision`'a yuvarlamak ilkinde tick'e oturmayan fiyat, ikincisinde gereksiz
hassasiyet üretirdi. Kaynağın `Filters` olması kararı mainnet'te de doğru.

`minNotional` mainnet'te sembole göre değişiyor (50 / 20 / 5). Kilitli karar 80 USDT notional
üçünün de üstünde.

## 3. Diğer imzasız bulgular

| Konu | Sonuç |
|---|---|
| Saat sapması | **+77,7 ms** (RTT 421,7 ms) — `recvWindow` 5000 ms'nin çok altında |
| Koşullu emir ucu (`/fapi/v1/openAlgoOrders`) | **var**: imzasız çağrı 401 `-2014` döndü, 404 değil |
| Sembol durumu | BTCUSDT / ETHUSDT / SOLUSDT `TRADING` |

## 4. Doğrulanamayanlar — mainnet anahtarı yok

Bu makinede mainnet API anahtarı **bulunmuyor**: `.env` yalnız testnet anahtarını taşıyor. Bu
bilinçli bir duruştur (CLAUDE.md güvenlik bölümü: mainnet anahtarı hiçbir trading container'ına
bağlanmaz).

Dolayısıyla şunlar doğrulanamadı:

| Konu | Neden | Ne gerekir |
|---|---|---|
| `-4130` davranışı (ADR 0023) | **açık pozisyon gerektirir** | mainnet anahtarı + gerçek para |
| Private WS URL biçimi | listenKey imzalı çağrı ister | mainnet anahtarı (para riski yok) |
| listenKey keepalive / `listenKeyExpired` | aynı | mainnet anahtarı (para riski yok) |
| Pozisyon modu (ONE-WAY / HEDGE) | imzalı | mainnet anahtarı (para riski yok) |
| Çoklu varlık teminat modu | imzalı | mainnet anahtarı (para riski yok) |
| Bakiye ve teminat alanları | imzalı | mainnet anahtarı (para riski yok) |

Bunların **beşi para riski taşımaz**; yalnız okuma yapar. Yalnız `-4130` doğrulaması gerçek
pozisyon açmayı gerektirir.

### `-4130` mainnet doğrulaması ne maliyet çıkarır

Testnet ölçümünün aynısı mainnet'te şu anlama gelir: BTCUSDT'de en küçük miktar (0,001 BTC ≈ 77
USDT notional, `minNotional` 50'nin üstünde), 10x kaldıraçla ~8 USDT teminat, pozisyon birkaç
saniye açık. Beklenen doğrudan maliyet iki taker komisyonu (~0,08 USDT) artı o saniyelerdeki fiyat
hareketi.

**Ölçülmüş risk:** testnet koşusunda temizlik adımı bir kez `-1021` (recvWindow) ile başarısız oldu
ve pozisyon açık kaldı; elle kapatıldı. Betik o koşudan sonra üç denemeli, taze damgalı kapatma ile
sertleştirildi ama mainnet'te aynı hata gerçek bir açık pozisyon bırakır.

Ayrıca Faz 10 (küçük sermaye ile canlı) **açılmadı** ve CLAUDE.md canlı emir yolunu proje sahibi
onayına bağlıyor. Bu yüzden mainnet `-4130` ölçümü yapılmadı; karar proje sahibinindir.

## BU DOĞRULAMADA YAPILMAYANLAR

- Mainnet'e **tek bir emir gönderilmedi**, imzalı tek bir istek yapılmadı.
- ADR 0023'ün kararı mainnet'te doğrulanmadı; testnet kanıtına dayanıyor ve bu belge bunu açıkça
  söylüyor.
- Mainnet WS akışlarının (`/public`, `/market`) çalıştığı ayrıca ölçülmedi; `fbot-recorder` 45
  saattir kesintisiz kayıt aldığı için bu yol zaten üretimde doğrulanmış sayılır.
