# ADR 0009 — Faz 3 veri kaynağı: Binance geçmiş aggTrades (ADR 0008 §1'in üstüne)

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi talebi: "Binance geçmiş veri veriyor zaten, neden bekliyoruz")

## Bağlam
ADR 0008 §1 araştırmayı yalnızca Faz 1 kaydına bağlıyordu; gerekçe look-ahead ve format tutarlılığıydı. Bu gerekçe kline verisi için geçerlidir (bar içi hareket bilinmez), ama ham aggTrade geçmişi için geçerli değildir: her işlemin zamanı (`transact_time`), fiyatı, miktarı ve agresör bayrağı (`is_buyer_maker`) vardır; Faz 2 bar üreticisi bunlardan canlıyla **aynı** barları üretir. Bekleme yalnızca örneklem büyüklüğü içindi; geçmiş veri bunu çözer.

Doğrulanan kaynak (2026-09-10): `https://data.binance.vision/data/futures/um/daily/`
- `aggTrades/<SYMBOL>/<SYMBOL>-aggTrades-YYYY-MM-DD.zip` — 2019-12-31'den beri; CSV başlığı `agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker`; ertesi gün yayında; `.CHECKSUM` (SHA-256).
- `markPriceKlines/<SYMBOL>/1m/…` ve `premiumIndexKlines/<SYMBOL>/1m/…` — 1 dk mark fiyatı ve premium index.
- `bookTicker` günlük dosyaları 2023-05'ten sonra **yok** (2025/2026 için 404). `bookDepth` var ama spread değil.

## Karar
1. Faz 3'ün birincil veri kaynağı geçmiş `aggTrades` (+ `markPriceKlines`, `premiumIndexKlines`, REST funding geçmişi). Kapsam: TOP 10 sembol, son 30 gün ile başlanır; gerekirse genişletilir.
2. Barlar **Faz 2 `SymbolMarket` ile** üretilir (aynı kod yolu); test: sentetik işlem dizisi için geçmiş yolu ve çekirdek bit-eşit bar üretir.
3. Spread: sembol başına, Faz 1 kaydından ölçülen bookTicker spread **medyanı**, sabit. Raporda "sabit spread" ibaresi zorunlu. Faz 1 kaydı büyüdükçe güncellenir.
4. Funding: REST `fundingRate` geçmişi; bar için `next_funding_ms` = bar bitişinden sonraki ilk funding anı, `funding_rate` = o anda gerçekleşen oran. Bu küçük bir look-ahead'dir (canlıda tahmini oran görülür); maliyet kalemi olarak etkisi ≤ %0.01 ve raporda not düşülür.
5. Faz 1 kaydı araştırmada **doğrulama** amaçlı kalır: aynı günün kayıt-barları ile geçmiş-barları karşılaştırılır (tutarlılık testi); canlı gecikme ve bayatlık yalnızca kayıttan ölçülür.
6. İndirme: stdlib (`urllib`, `zipfile`, `hashlib`), checksum doğrulanmadan dosya kullanılmaz. Yeni bağımlılık yok.

## Sonuçlar
- Faz 3 nihai raporu 3 gün beklemeden, 30 günlük veriyle bugün üretilebilir; 60 dk ufkunda hücre başına n ≥ 100 rahatça sağlanır.
- ADR 0008'in diğer maddeleri (keşif/doğrulama ayrımı, örtüşmeyen örnekleme, bootstrap, karar kuralı) değişmez.
- Sembol evreni "bugünün TOP 10'u" olduğu için hayatta kalma yanlılığı vardır: bugün hacimli olan sembollerin geçmişi seçilmiştir. Raporda belirtilir; Faz 6'da evren günlük yenilendiği için canlıda bu yanlılık yoktur.
