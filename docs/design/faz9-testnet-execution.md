# Faz 9 tasarım notu — testnet canlı execution

Tarih: 2026-09-10 · Durum: tasarım notu, kod yok. Bu fazda `LiveExecutionAdapter` stub'ı **proje sahibi onayıyla** gerçek implementasyona dönüşür; testnet'e bağlıdır, mainnet URL'si bu fazda kodda bile yer almaz.

## 1. Doğrulanmış uç noktalar (docs/binance-api-verification.md)
| Yüzey | Testnet |
|---|---|
| REST | `https://demo-fapi.binance.com` |
| WS API (emir) | `wss://testnet.binancefuture.com/ws-fapi/v1` |
| Market stream | `wss://demo-fstream.binance.com` (`/public`, `/market`, `/private` yolu Faz 9'da doğrulanır) |

## 2. Kimlik ve güvenlik
- Ed25519 anahtar çifti: özel anahtar PKCS#8 PEM, yalnızca `.env` yoluyla, dosya izni 600, repo/log/image dışında. İmza için kütüphane gerekir (**stdlib'de Ed25519 yok**): `cryptography` ya da `pynacl` — ADR + onay.
- API anahtarı: çekim yetkisi **kapalı**, IP whitelist **açık**; program açılışta anahtar izinlerini sorgular (izin sorgulama endpoint'i Faz 9'da doğrulanır) ve çekim açıksa çalışmayı reddeder.
- `session.logon` sonrası `apiKey`/`signature` parametreleri atlanır (doğrulandı); `session.status` ile periyodik doğrulama; bağlantı 24 saat, ping 3 dk / pong 10 dk.
- User data: `userDataStream.start` → listenKey → `/private/ws?listenKey=…&events=…`; keepalive 30 dk; `listenKeyExpired` → yeniden başlat + mutabakat (ADR 0003).

## 3. Emir yaşam döngüsü (WS API)
- `order.place` (giriş, reduceOnly çıkış), `order.cancel`, `order.status`; `algoOrder.place` / `algoOrder.cancel` (SL/TP, `closePosition=true`, `workingType`, `priceProtect`); `order.modify` yalnızca LIMIT.
- Order state machine (çekirdekte, saf): NEW → PARTIALLY_FILLED → FILLED / CANCELED / EXPIRED / **EXPIRED_IN_MATCH** / REJECTED; algo: NEW → TRIGGERED → (order state) / CANCELED / EXPIRED. Kaynak: `ORDER_TRADE_UPDATE`, `ALGO_UPDATE` (payload alanları Faz 9'un ilk işi olarak dokümandan doğrulanır).
- Idempotency: deterministik `newClientOrderId` / `clientAlgoId` (Faz 4 şeması); cevap kaybı / 503 UNKNOWN → `order.status` ile mutabakat, sonra aynı id ile yeniden gönderim (id çakışması = zaten gönderilmiş demektir).
- Rate limit: iki token bucket, header/`rateLimits` ile senkron; 429 → geri çekilme; 418 → kill switch.

## 4. Test planı (testnet, her biri otomatik ve tekrarlanabilir)
1. Logon, status, logout; anahtar izin kontrolü.
2. Tam döngü: maker giriş → fill → SL+TP algo → SL tetik → TP iptal; ters senaryo (TP tetik → SL iptal). **OCO var mı** ölçülür.
3. "Önce yeni, sonra eski iptal" SL değiştirme sırası: iki `closePosition` açıkken tetik → tek kapanış, ters pozisyon yok (Faz 4 §5 varsayımının kanıtı).
4. reduceOnly çıkış ile borsa stop çakışması → `-2022` beklenen ret.
5. `countdownCancelAll` × algo emir etkileşimi (yalnızca gözlem; kararı ADR'ye).
6. Cevap kaybı simülasyonu (bağlantıyı kes) → mutabakat → idempotent yeniden deneme.
7. Private stream kopması, listenKey süresi dolması, yeniden bağlanma + mutabakat.
8. Kısmi dolum (büyük LIMIT ile yapay), STP `EXPIRED_IN_MATCH` (iki anahtarla mümkünse), sembol filtresi ihlali (-1111/-4164), PERCENT_PRICE ihlali.
9. Kill switch açıkken giriş reddi, çıkış serbestliği; restart sonrası kill switch kalıcılığı.
10. Fill gecikmesi ölçümü: `order.place` → ACK → `ORDER_TRADE_UPDATE`; Faz 0 baseline ile karşılaştırma.

## 5. Kapı
Prompt: "testnet'te en az 2 hafta hatasız". Proje sahibi kapı sürelerini 1 saate indirdi (ADR 0006); Faz 9 için süre **proje sahibi kararı**. Öneri: süre yerine test planındaki 10 maddenin tamamının geçmesi + en az 100 gerçek testnet emri döngüsü.

## 6. Sorular
1. Ed25519 için `cryptography` mı `pynacl` mi? (Öneri: `cryptography`, yaygın.)
2. Testnet anahtarını ne zaman vereceksin? Faz 9 başlangıcında `.env` ile.
3. Kapı: süre mi, test sayısı mı?

## 7. Olmayanlar
Mainnet URL'leri, canlı anahtar, sermaye.
