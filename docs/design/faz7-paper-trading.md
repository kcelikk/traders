# Faz 7 tasarım notu — paper trading (canlı veri + simüle execution)

Tarih: 2026-09-10 · Durum: tasarım notu, kod yok. Başlangıç koşulu: Faz 3 geçti, Faz 4–6 kapandı. Süre: **en az 4 hafta** (kilitli).

## 1. Amaç
Canlı veri üzerinde, gerçek emir göndermeden, tüm karar zincirini (state → decision → risk → position manager) çalıştırmak ve sonucu backtest ile karşılaştırmak. Kapı: paper sonuçları replay/backtest ile tutarlı; sapma varsa nedeni açıklanmış.

## 2. Topoloji
- Process 1 `trader` (paper modu): Faz 1 gateway'i (public/market bağlantıları) + Faz 2 çekirdek + Faz 4–6 modüller + `PaperExecutionAdapter`. Tek thread, tek döngü; recorder aynı process'te kayda devam eder (ADR 0005). Private stream yok (anahtar yok).
- Process 3 `persistence`: kararlar, intent'ler, simüle emirler/fill'ler, pozisyonlar, risk kararları, state geçişleri. **Öneri: SQLite (stdlib), write-behind, tek yazar.** Postgres yalnızca ölçülmüş ihtiyaçta (ADR Faz 7 başında).
- Bus: process 1'den dışarı fire-and-forget; teknoloji seçimi Faz 8 ADR'si (aşağıda). Faz 7'de en basit yol: process 1 kararları kayıt akışına `ctrl/decision` olayı olarak yazar; persistence kayıt dosyalarını okur (bus'sız, kayıp riski sıfır, gecikme saniyeler). Yeterlidir çünkü paper'da hiçbir tüketici gerçek zamanlı değildir.

## 3. Fill modeli (`PaperExecutionAdapter`, saf + seed'li)
| Emir | Dolum kuralı | Fiyat | Maliyet |
|---|---|---|---|
| Maker giriş (GTX/QUEUE) | kuyruk pozisyonu bilinmez → **muhafazakâr**: fiyat limitten geçince (long için aggTrade `p < limit`) dolar; eşitlikte dolmaz | limit | maker komisyonu |
| Taker (MARKET, reduceOnly) | karar anı + simüle gecikme sonrası ilk bookTicker | karşı taraf best ± defter yürüyüşü (depth@100ms'ten, Faz 2 `slippage_cost`) | taker komisyonu |
| Algo SL/TP (`closePosition`) | mark fiyatı (`markPrice@1s`) tetik seviyesini geçince; tetik sonrası MARKET gibi dolar | tetik sonrası ilk bookTicker karşı taraf + yürüyüş | taker |
| Funding | her funding anında `markPrice` `r` ile pozisyon notional × oran | — | funding |

- **Gecikme simülasyonu:** karar → emir kabulü ve tetik → dolum arasına Faz 0'da ölçülen dağılımdan seed'li örnek (p50 0.42 s, p99 1 s; ampirik dağılım dosyadan). Seed config'de.
- Kısmi dolum yok (80 USDT notional tek seviyede dolar; ölçüldü). Bu varsayım raporda yazılır.
- STP simüle edilmez (tek hesap).

## 4. Tutarlılık testi (kapı)
Aynı 4 haftanın kaydı üzerinde offline replay (Faz 2 harness + aynı modüller + aynı seed) ile paper'daki gerçek zamanlı koşu **karar dizisi** (intent, risk verdict, çıkış kararı) bit-eşit olmalı. Fark yalnızca gecikme kaynaklı dolum farkı olabilir; o da raporlanır (fill farkı sayısı, PnL farkı). Bu, Rule Zero'nun canlı koşuya uzatılmasıdır.

## 5. Raporlama (BÖLÜM 12 asgari seti)
Toplam getiri, net PnL, brüt kâr/zarar, kazanma oranı, ortalama kazanç/kayıp, profit factor, beklenti, maksimum drawdown, risk-ayarlı ölçüt (öneri: net PnL / maks drawdown), işlem sayısı, ortalama tutma süresi, **komisyon toplamı, funding toplamı, slippage toplamı**, çıkış nedeni dağılımı, **kârdan zarara dönen pozisyon oranı**, state geçiş istatistikleri, maliyet sürüklenmesi metrikleri (6.4). Haftalık ara rapor; 4 hafta sonunda kapı raporu.

## 6. Kabul kriterleri (taslak)
1. 4 hafta kesintisiz (restart'lar raporda); bayatlık/kill olayları listelenir.
2. Tutarlılık testi geçer.
3. Paper net beklenti, Faz 3 hücre beklentileriyle uyumlu (sapma açıklanır; "uyumlu" eşiği: %95 CI içinde).
4. Fill modeli varsayımları listelenir; Faz 9 testnet'te gerçek fill'lerle karşılaştırılacak.

## 7. Proje sahibine sorular
1. SQLite kabul mü (yeni bağımlılık yok)?
2. 4 hafta kuralı kalıyor mu? (Kilitli; değiştirilmesi ADR ister.)

## 8. Bu notta olmayanlar
Sayısal eşikler; bus teknolojisi (Faz 8); gerçek emir yolu.
