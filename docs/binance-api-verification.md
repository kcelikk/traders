# Binance USDⓈ-M Futures API doğrulama kaydı

Tarih: 2026-09-10. Kaynak: `developers.binance.com` (Derivatives → USDⓈ-M Futures) ve changelog.
Yöntem: her sayfa çekildi, ilgili cümle alıntılandı. Alıntılanamayan hiçbir şey "doğrulandı" sayılmadı.

Durum kodları: **DOĞRULANDI** · **DEĞİŞTİ** (prompt varsayımı eskimiş) · **BULUNAMADI** · **KISMİ**

---

## 1. WebSocket URL bölünmesi (prompt 4.1)

| İddia | Durum | Kaynak / alıntı |
|---|---|---|
| Public / Market / Private ayrımı | DOĞRULANDI | `wss://fstream.binance.com/public`, `/market`, `/private` — [Important WebSocket Change Notice](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Important-WebSocket-Change-Notice) |
| Eski URL'ler 2026-04-23'te kapandı | DOĞRULANDI | "Legacy URLs will remain available until 2026-04-23" (aynı sayfa); changelog 2026-04-02 girişi `wss://fstream-auth.binance.com` için de aynı tarih |
| `/public`: `@bookTicker`, `!bookTicker`, `@depth*` | DOĞRULANDI | `<symbol>@bookTicker`, `!bookTicker`, `<symbol>@depth<levels>`, `<symbol>@depth` |
| `/market`: aggTrade, markPrice, kline, ticker, miniTicker, forceOrder, compositeIndex, !contractInfo, assetIndex | DOĞRULANDI | Liste birebir; ek olarak `continuousKline`, `!markPrice@arr`, `!assetIndex@arr` |
| Sessiz veri kaybı tuzağı | DOĞRULANDI | "any connections not migrated will ONLY be able to receive data from wss://fstream.binance.com/public" — `/ws/btcusdt@markPrice` örneği veri almaz |
| Bağlantı ömrü 24 saat | DOĞRULANDI | "A single connection to the API is only valid for 24 hours" (WS API General Info; market stream sayfası arama özetinde aynı ifade) |
| Sunucu ping 3 dk, pong 10 dk | DOĞRULANDI | "ping frame every 3 minutes … 10 minute period" |
| Bağlantı başına maks stream | DOĞRULANDI | 1024 (changelog 2025-07-02: 200 → 1024) |
| Gelen mesaj limiti | DOĞRULANDI | "10 incoming messages per second"; ping/pong çerçeveleri için "maximum 5 per second" |
| Raw / combined stream biçimi | DOĞRULANDI | `/public/ws/{symbol}@bookTicker`, `/public/stream?streams=…`, ayrıca `/market/stream` + SUBSCRIBE mesajı |
| Testnet market stream URL | DOĞRULANDI | `wss://demo-fstream.binance.com` (arama özeti; Faz 9'da sayfadan tekrar teyit) |

**Mimari sonuç:** kategori başına ayrı bağlantı ve ayrı bayatlık izleyicisi zorunlu (prompt ile uyumlu).

## 2. User data stream ve kimlik doğrulama (prompt 4.2) — **KİLİTLİ KARARLA ÇELİŞKİ**

| İddia | Durum | Kaynak / alıntı |
|---|---|---|
| WS API `wss://ws-fapi.binance.com/ws-fapi/v1` | DOĞRULANDI | [WebSocket API General Info](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info); testnet `wss://testnet.binancefuture.com/ws-fapi/v1` |
| `session.logon` Ed25519 gerektirir | DOĞRULANDI | "Only Ed25519 keys are supported for this feature"; `session.status`, `session.logout` da var |
| WS API imza payload'ı | DOĞRULANDI | "taking all request params except for the signature and sorting them by name in alphabetical order" |
| `userDataStream.subscribe` ile abonelik | **BULUNAMADI (Futures'ta yok)** | Futures WS API user data metotları yalnızca `userDataStream.start`, `userDataStream.ping`, `userDataStream.stop` — [katalog sayfası](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-api/user-data-streams). `userDataStream.subscribe` yalnızca **Spot** dokümanında var. |
| listenKey terk ediliyor | **DEĞİŞTİ / DOĞRULANAMADI** | Futures'ta listenKey hâlâ tek mekanizma: "The stream will close after 60 minutes unless a keepalive is sent … recommended to send a ping about every 60 minutes". Private bağlantı örneği: `wss://fstream.binance.com/private/ws?listenKey=<listenKey>&events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE`. Futures changelog'unda listenKey deprecation girişi yok. |
| Volatil piyasada REST gecikir, user data stream tavsiye | DOĞRULANDI | "During an extremely volatile market, it is highly recommended to get the order status, position, etc from the Websocket user data stream due to possible data latency from RESTful endpoints." |

**Sonuç:** "session.logon + userDataStream.subscribe, listenKey keepalive döngüsü yazma" kararı bugünkü Futures dokümanıyla **uygulanamaz**. Ayrıntı ve öneri ADR 0003'te. **Proje sahibi kararı gerekiyor.**

## 3. Koşullu emirler (prompt 4.3) — **BÜYÜK DEĞİŞİKLİK**

| İddia | Durum | Kaynak / alıntı |
|---|---|---|
| STOP_MARKET / TAKE_PROFIT_MARKET `POST /fapi/v1/order` ile | **DEĞİŞTİ** | Changelog 2025-11-06, yürürlük 2025-12-09: "Conditional orders migrated to Algo Service". Eski endpoint'te hata **-4120** "Order type not supported for this endpoint. Please use the Algo Order API endpoints." |
| Yeni koşullu emir endpoint'i | DOĞRULANDI | `POST /fapi/v1/algoOrder`, `algoType=CONDITIONAL`, tipler: `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `STOP`, `TAKE_PROFIT`, `TRAILING_STOP_MARKET` — [New Algo Order](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order). WS API: `algoOrder.place`, `algoOrder.cancel`. Sayaç: "1 on 10s order rate limit; 1 on 1min order rate limit; 0 on IP rate limit" |
| Tetik fiyatı parametresi | DEĞİŞTİ | `stopPrice` değil **`triggerPrice`**; client id **`clientAlgoId`**; kimlik **`algoId`** |
| `closePosition=true` + quantity/reduceOnly yasak | DOĞRULANDI | Hata kodları -4137 "Quantity must be zero with closePosition equals true", -4138 "Reduce only must be true with closePosition equals true" |
| `workingType` CONTRACT_PRICE / MARK_PRICE, `priceProtect` | DOĞRULANDI | Algo order parametre tablosunda; `priceProtect` default `false` |
| `priceMatch` OPPONENT/QUEUE | KISMİ | Var; ancak changelog 2025-10-21: `OPPONENT_10` ve `OPPONENT_20` "temporarily removed" |
| Emir değiştirme (amend) TP için tercih | **KISMİ — KISIT** | `PUT /fapi/v1/order`: "currently only LIMIT order modification is supported"; "modified orders will be reordered in the match queue"; "One order can only be modified for less than 10000 times". **Algo (koşullu) emirler için modify endpoint'i yok** → koşullu SL/TP güncellemesi zorunlu olarak cancel + place. |
| Koşullu emir bildirimleri | DEĞİŞTİ | Yeni `ALGO_UPDATE` event'i; `CONDITIONAL_ORDER_TRIGGER_REJECT` 2025-12-15 itibarıyla kaldırıldı; algo emir tetiklenince asıl emir `ORDER_TRADE_UPDATE` ile gelir (payload Faz 1'de doğrulanacak) |
| Koşullu emir limiti | DOĞRULANDI | Changelog 2025-12-29: `MAX_NUM_ALGO_ORDERS` filtresi kaldırıldı, "conditional order limit set at 200 across symbols" |
| STP ve `EXPIRED_IN_MATCH` | DOĞRULANDI | Modlar `EXPIRE_TAKER`, `EXPIRE_MAKER`, `EXPIRE_BOTH`; durum `EXPIRED_IN_MATCH`; GTC/IOC/GTD'de geçerli, FOK/GTX'te değil; modify STP'yi NONE'a sıfırlar — [STP FAQ](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq) |
| Yeni emir tipleri/TIF | DOĞRULANDI | `timeInForce`: GTC, IOC, FOK, GTX, GTD, **RPI** (2025-11-18) |

## 4. Rate limitler (prompt 4.4)

| İddia | Durum | Kaynak / alıntı |
|---|---|---|
| Ağırlık ve emir sayaçları ayrı | DOĞRULANDI | IP: `X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)`; hesap: `X-MBX-ORDER-COUNT-(intervalNum)(intervalLetter)` — [General Info](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info) |
| Emir IP ağırlığı tüketmez | DOĞRULANDI | New Order / Algo Order / Modify: "0 on IP rate limit", 10s ve 1m emir sayaçlarında 1'er |
| 10 s ve 1 dk emir limitleri | DOĞRULANDI | WS API örnek cevabı: `ORDERS`, `SECOND`, `intervalNum 10`, `limit 300` |
| REQUEST_WEIGHT limiti | DOĞRULANDI | exchangeInfo örneği: `MINUTE / 1 / 2400` |
| 429 → geri çekil, 418 → dur | DOĞRULANDI | "A 429 will be returned when either rate limit is violated"; 418 "auto-banned"; "IP bans … scale in duration … from 2 minutes to 3 days" |
| WS API sayaçları | DOĞRULANDI | `REQUEST_WEIGHT` per-IP ve REST'ten **ayrı**; `ORDERS` per-UID ve REST ile **paylaşımlı**; her cevapta `rateLimits` alanı; `returnRateLimits` ile kapatılabilir; handshake 5 ağırlık |
| 503 "Unknown error" | DOĞRULANDI (ek bulgu) | "execution status is UNKNOWN" — asla başarısız sayma, mutabakat gerekir |

## 5. Auto-cancel (prompt 4.5)

| İddia | Durum | Kaynak / alıntı |
|---|---|---|
| `countdownCancelAll` mevcut | DOĞRULANDI | `POST /fapi/v1/countdownCancelAll`, IP ağırlık 10, `countdownTime` ms, `0` kapatır; "should be called repeatedly as heartbeats" |
| Koşullu (algo) emirleri de iptal ediyor mu | **BİLİNMİYOR** | Sayfa algo emirlerden söz etmiyor. Algo emirler artık ayrı serviste; davranış Faz 9'da testnet'te ölçülecek. Karar değişmez: koruma emirlerine asla uygulanmaz. |

## 6. Sembol filtreleri (prompt 4.6)

DOĞRULANDI — `GET /fapi/v1/exchangeInfo` (ağırlık 1): `PRICE_FILTER` (tickSize, min/maxPrice), `LOT_SIZE`, `MARKET_LOT_SIZE`, `MAX_NUM_ORDERS`, `PERCENT_PRICE` (multiplierUp/Down/Decimal), `MIN_NOTIONAL` (notional). `MAX_NUM_ALGO_ORDERS` dokümanda listeleniyor ama changelog 2025-12-29 kaldırıldığını söylüyor → çelişki, canlı çıktıdan teyit edilecek. Sembol alanları: `pricePrecision`, `quantityPrecision`, `contractType`, `status`, `liquidationFee`, `marketTakeBound`. Hata -4131: "counterparty's best price does not meet the PERCENT_PRICE filter limit"; -4164 MIN_NOTIONAL (reduceOnly muaf).

## 7. İmzalama ve zaman (prompt 4.7)

| İddia | Durum | Kaynak / alıntı |
|---|---|---|
| REST imza | DOĞRULANDI | HMAC SHA256 (`totalParams` = query string + request body) ve RSA PKCS#8. **Futures REST General Info sayfasında Ed25519 geçmiyor.** Ed25519 yalnızca WS API'de zorunlu. |
| Parametre çakışması | DOĞRULANDI | "If a parameter sent in both the query string and request body, the query string parameter will be used." |
| `recvWindow` | DOĞRULANDI | Varsayılan 5000, maks 60000; kabul koşulu: `timestamp < serverTime + 1000 && serverTime - timestamp <= recvWindow`; hata -1021 |
| REST base | DOĞRULANDI | Mainnet `https://fapi.binance.com`; **testnet `https://demo-fapi.binance.com`** |
| Zaman/ping endpoint'leri | DOĞRULANDI (ampirik) | `GET /fapi/v1/ping` HTTP 200, `GET /fapi/v1/time` → `{"serverTime": …}` bu sunucudan çalıştırıldı |

## 8. Maliyet kaynakları (prompt 6)

| Öğe | Durum | Kaynak |
|---|---|---|
| Income endpoint | DOĞRULANDI | `GET /fapi/v1/income`, ağırlık 30, `incomeType` ∈ {TRANSFER, WELCOME_BONUS, REALIZED_PNL, FUNDING_FEE, COMMISSION, INSURANCE_CLEAR, REFERRAL_KICKBACK, COMMISSION_REBATE, … (toplam 22)}; "last three months"; `page`, `limit` ≤ 1000 |
| Funding geçmişi | DOĞRULANDI | `GET /fapi/v1/fundingRate` (fundingRate, fundingTime, markPrice, `rateType` Regular/Special); `GET /fapi/v1/fundingInfo` (`fundingIntervalHours`, cap/floor) — ikisi 5 dk'da 500 paylaşımlı limit |
| Hesap komisyon oranı | DOĞRULANDI (anahtar gerekir) | `GET /fapi/v1/commissionRate` — [User Commission Rate](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate) |
| Ücret tablosu sayısal değerleri | **DOĞRULANAMADI** | Resmi ücret sayfası ve FAQ (son güncelleme 2026-05-01) tabloyu login'siz render etmiyor. Resmi olarak yalnızca "10% discount … when they use BNB" alıntılandı. Üçüncü taraf kaynaklar VIP0 maker %0.02 / taker %0.05 diyor → unit economics'te **"üçüncü taraf, doğrulanmadı"** etiketiyle kullanılacak, hesaptan `commissionRate` ile düzeltilecek. |

## 9. Stream payload alanları (ölçüm için)

| Stream | Kategori | Zaman alanları | Kaynak |
|---|---|---|---|
| `<symbol>@aggTrade` | /market | `E` event time, `T` trade time; hız 100 ms; `nq` RPI hariç miktar | [market katalog](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market) |
| `<symbol>@bookTicker` | /public | `E` event time, `T` transaction time, `u` updateId; hız real-time | [public katalog](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public) |
| `<symbol>@markPrice@1s` | /market | `E`; `p` mark, `i` index, `r` funding, `T` next funding, `ap` MA | market katalog |
| `<symbol>@depth@100ms` | /public | `E`, `T`, `U`, `u`, `pu` | public katalog |

## 10. Faz 1'e ertelenen doğrulamalar

- `ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE`, `ALGO_UPDATE`, `listenKeyExpired` payload alanları (sayfalar SPA nedeniyle çekilemedi; Faz 1'de tarayıcı veya raw HTML ile alınacak).
- Local order book yönetimi kuralları (depth snapshot + `pu` zinciri).
- WS API `order.modify`, `order.cancel`, `algoOrder.place` parametre tabloları.
- `countdownCancelAll` × algo emir etkileşimi (testnet).
- `MAX_NUM_ALGO_ORDERS` filtresinin canlı `exchangeInfo` çıktısında olup olmadığı.
