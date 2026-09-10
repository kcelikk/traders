# ADR 0004 — Sembol evreni, işlem büyüklüğü, kaldıraç, açılışta zorunlu SL/TP

Tarih: 2026-09-10 · Durum: **KABUL EDİLDİ** (proje sahibi, 2026-09-10; açık sorular kapandı, bkz. son bölüm)

## Proje sahibi kararları (2026-09-10)

1. Başlangıç sembol evreni: **TOP 10** (önceki kilitli karar "1–3 ile başla" proje sahibi tarafından değiştirildi; üst sınır 20 korunuyor).
2. Kaldıraç: **5x ve 10x**, sembol başına config.
3. **Her işlem 10 $.**
4. **Her pozisyon açılırken stop-loss ve take-profit girilir.**
5. Kâr/zarar ve bütçe kaldıraca bağlı olarak doğru hesaplanır.

## Ölçümle karşılaştırma (exchangeInfo + ticker/24hr, 2026-09-10 07:44 UTC)

Gerçek minimum notional = max(`MIN_NOTIONAL`, `minQty` × fiyat), `stepSize`'a yuvarlı:

| Sembol | min notional gerçek | teminat 5x | teminat 10x |
|---|---|---|---|
| BTCUSDT | 78.0 USDT (0.001 BTC) | 15.6 | 7.8 |
| ETHUSDT | 22.2 USDT | 4.4 | 2.2 |
| diğer 8 (ZEC, SOL, IOST, XRP, HYPE, DOGE, NEAR, BNB) | 5.0–7.2 USDT | 1.0–1.4 | 0.5–0.7 |

**Sonuç:** "10 $" **teminat** ise 10x'te tüm TOP 10 açılabilir, 5x'te BTCUSDT açılamaz (50 USDT notional < 78 USDT gerçek minimum). "10 $" **notional** ise BTCUSDT ve ETHUSDT hiçbir kaldıraçta açılamaz (minimum 78 / 22.2 USDT). Kaldıraç MIN_NOTIONAL'ı değiştirmez; yalnızca teminatı böler.

Maliyet etkisi (unit economics, taker/taker %0.10 gidiş-dönüş): 10 $ teminat, 10x → 100 USDT notional → işlem başına 0.10 USDT komisyon = **teminatın %1'i**. 5x → 50 USDT notional → 0.05 USDT = teminatın %0.5'i. Günde 20 işlemde 10x'te teminatın %20'si komisyona gider.

## Tasarım sonuçları

- **Pozisyon boyutlandırma** Risk Engine'de: `notional = teminat × kaldıraç`; miktar `stepSize`'a aşağı yuvarlanır; sonuç `MIN_NOTIONAL` ve `minQty` altındaysa **REJECT** (yukarı yuvarlayıp bütçeyi aşmak yok). Filtreler açılışta `exchangeInfo`'dan çekilir, periyodik yenilenir.
- **Kaldıraç muhasebesi:** PnL notional üzerinden hesaplanır (`(çıkış − giriş) × miktar`), teminat üzerinden değil. ROE = PnL / teminat. Komisyon ve funding notional üzerinden. Likidasyon fiyatı ve bakım teminatı Binance'ın kendi hesabından (`ACCOUNT_UPDATE` ve pozisyon risk endpoint'i) okunur, iç formül yalnızca tahmin ve mutabakat içindir.
- **Bütçe:** kullanılabilir teminat = cüzdan bakiyesi − açık pozisyonların başlangıç teminatı − açık emirlerin teminat rezervi; borsa değeri (`availableBalance`) tek doğruluk kaynağı, iç hesapla mutabakat yapılır. Sapmada trading kilitlenir.
- **Açılışta SL + TP:** giriş emri dolduğunda (`ORDER_TRADE_UPDATE` FILLED) iki algo emir gönderilir: `STOP_MARKET` ve `TAKE_PROFIT_MARKET`, ikisi de `closePosition=true`, `workingType` config'den, deterministik `clientAlgoId`. Giriş dolmadan koruma emri gönderilmez (pozisyon yokken closePosition emri reddedilir mi → Faz 9'da doğrulanacak). Biri tetiklenince diğeri **iptal edilmek zorunda**; USDⓈ-M'de OCO benzeri bir bağlama olup olmadığı dokümandan doğrulanacak, yoksa uygulama iptal eder ve bu bir yarış penceresidir (Katman 1 tek sahiplik kuralı).
- Uygulama tarafı akıllı çıkış (Katman 2) korunur; TP statik güvenlik ağıdır, tek çıkış değil. SL ve TP mesafeleri Faz 3 verisi olmadan sabitlenmez; config'de "bilinmiyor".
- Sembol evreni "TOP 10" bir **liste değil kural** olarak tanımlanır (metrik + yenileme periyodu + stablecoin çiftlerinin dışlanması); listeye giren/çıkan sembol için ısınma ve açık pozisyon kuralları Faz 5'te.

## Kapanan sorular (proje sahibi, 2026-09-10)

1. **İşlem büyüklüğü: 80 USDT notional** (10 $ / 20 $ önerileri BTC ve ETH filtrelerine takıldığı için). Miktar `stepSize`'a aşağı yuvarlanır; sonuç filtre altıysa REJECT. Teminat: 5x'te 16 USDT, 10x'te 8 USDT. Taker/taker gidiş-dönüş komisyon ≈ 0.08 USDT/işlem (VIP0, doğrulanmadı) = teminatın %0.5 (5x) / %1 (10x).
   Ölçüm (2026-09-10): 80 USDT hedefle TOP 10'un tamamı açılır; BTC 0.001 BTC = 78.0 USDT (−2.5 %), diğerleri −4 % … 0 % sapma.
2. **TOP 10 kuralı:** USDT-margined PERPETUAL, `status=TRADING`, 24 saatlik `quoteVolume` sırası, stablecoin base'ler (USDC, FDUSD, TUSD, BUSD, USD1, USDE, USDP) hariç. **Günlük yenileme, 00:00 UTC.** Listeye giren sembol ısınma bekler; listeden çıkan sembolde yeni pozisyon açılmaz, açık pozisyon çıkış kurallarıyla yönetilir.
3. **Kaldıraç:** BTCUSDT ve ETHUSDT 10x, diğer tüm semboller 5x. Config'de sembol başına, kural varsayılan.
4. **SL/TP mesafesi:** Faz 3 verisinden türetilene kadar config'de `null` ("bilinmiyor"); Faz 1–2 yalnızca altyapı. Değer olmadan pozisyon açılmaz (fail-closed).
