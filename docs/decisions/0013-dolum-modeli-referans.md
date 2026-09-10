# ADR 0013 — Paper dolum modeli: kanıtlanmış referanslara dayandırma

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi: "sıfırdan yazmak yerine çalıştığını bildiğin standart bir kaynaktan faydalan… testnet istemiyorum, gerçek data")

## Bağlam
Faz 7'de yazılan `fbot/execution/sim.py` dolum varsayımları ölçülmemişti: emirler karşı taraftaki en iyi fiyattan dolar, kısmi dolum yok, kuyruk pozisyonu yok, gecikme sabit 400 ms. Bunlar paper sonucunu iyimser gösterebilir.

Proje sahibi iki sınır koydu: **testnet kullanılmayacak**, veri **gerçek (mainnet) kayıt** olacak. Dolayısıyla "çalıştığı bilinen kaynak", bir borsa ortamı değil, olgun açık kaynak simülatörlerin **doğrulanmış dolum kuralları** olmalıdır.

## İncelenen kaynaklar (2026-09-10, resmi dokümandan alıntı)

| Kaynak | Lisans | Doğrulanan kural |
|---|---|---|
| **NautilusTrader** (backtest matching engine) | LGPL-3.0 | MARKET emirler "walk crossed book levels as a taker"; LIMIT emirler piyasa fiyatı geçerse taker, dururken maker; kısmi dolum "available crossed size is smaller than its remaining quantity" olduğunda; `STOP_MARKET` "walk crossed levels after triggering"; `prob_fill_on_limit` = fiyat dokunup geçmediğinde dolma olasılığı; `prob_slippage` = **yalnızca L1 defterlerde** bir tick aleyhte kayma, "does not apply to L2 or L3 books"; `random_seed` ile tekrarlanabilirlik; `price_protection_points` market emir kaymasını sınırlar |
| **Hummingbot** (paper_trade connector) | Apache-2.0 | Market emirler `simulate_buy`/`simulate_sell` ile defteri yürür, **ağırlıklı ortalama fiyat**; limit emir karşı taraf fiyatı limiti geçince dolar; `TRADE_EXECUTION_DELAY = 5.0` s kuyruklu yürütme; kuyruk pozisyonu ve kısmi dolum **yok** |

Ortak ve kanıtlanmış çekirdek: **L2 defter yürüyüşü + ağırlıklı ortalama + derinlik yetmezse kısmi dolum + açık gecikme modeli + seed'li rastlantı.**

## Seçenekler
1. **NautilusTrader'ı kütüphane olarak kullan.** Reddedildi: ADR 0001 gerekçeleri (Rust çekirdek, kendi veri modeli/bus, rc API) geçerli; yalnızca eşleştirme motorunu almak tüm veri tiplerini benimsemeyi gerektirir.
2. **LGPL kodu repoya kopyala.** Reddedildi: lisans bulaşması; proje kapalı kalabilir.
3. **Testnet'i yürütme ortamı olarak kullan.** Proje sahibi tarafından reddedildi (bu ADR'nin bağlamı).
4. **Doğrulanmış kuralları kendi veri yapılarımızla uygula, kaynağı belirt.** ✅ Seçilen.

## Karar
`SimExecutor` yeniden yazılır; kurallar yukarıdaki tabloda alıntılanan davranışlardır:

1. **Taker dolumu defter yürüyüşüyle.** Kaynak, Faz 1'de kaydedilen `@depth@100ms` akışından `fbot/orderbook.py` ile kurulan L2 defterdir (bu defter Faz 1'de REST snapshot'larıyla karşılaştırılıp seviye eşitliği %96.9–99.7 ölçüldü). Fiyat = tüketilen seviyelerin ağırlıklı ortalaması.
2. **Kısmi dolum.** Defter derinliği miktarı karşılamıyorsa dolan kadar dolar, kalan miktar bir sonraki defter güncellemesinde denenir; `partial_timeout_ms` sonunda kalan iptal edilir.
3. **Maker dolumu muhafazakâr.** Limit emir yalnızca piyasa fiyatı limiti **geçtiğinde** dolar (dokunma yetmez); `prob_fill_on_touch` (varsayılan 0.0) ile dokunmada dolum olasılığı açılabilir. Kuyruk pozisyonu modellenmez ve bu **raporda belirtilir**.
4. **Tetikleyiciler mark fiyatıyla.** `STOP_MARKET`/`TAKE_PROFIT_MARKET` tetiği `workingType=MARK_PRICE` (ADR 0012) ile Binance semantiğine uygun; tetik sonrası taker gibi defteri yürür.
5. **Gecikme açık ve seed'li.** `latency_ms` temel + `latency_jitter_ms` seed'li örnekleme (Faz 0 ölçümü: p50 ≈ 420 ms, p99 ≈ 1 s). Rastlantı yalnızca burada ve seed config'de (Rule Zero #5).
6. **L1 kayması yok.** Defter L2 olduğu için ek `prob_slippage` uygulanmaz (Nautilus'un "does not apply to L2/L3" kuralı).
7. **Defter yoksa emir bekler**, en iyi fiyattan doldurulmaz (eski davranışın iyimserliği kaldırıldı).

## Sonuçlar
- Paper sonuçları "defter derinliğinden ölçülmüş" slippage taşır; maliyet modeli (BÖLÜM 6) ile tutarlı olur.
- Kuyruk pozisyonu modellenmediği için **maker dolum oranı iyimserdir**; her paper raporunda bu not yer alır.
- Kayıt akışına `@depth@100ms` zaten dahildir; ek veri gerekmez.
- Kod bağımsız yazılır; NautilusTrader ve Hummingbot yalnızca davranış referansıdır (kod kopyalanmadı).
