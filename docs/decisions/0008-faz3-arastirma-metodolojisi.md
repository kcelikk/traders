# ADR 0008 — Faz 3: offline araştırma metodolojisi (DUR kapısı)

Tarih: 2026-09-10 · Durum: kabul edildi (hazırlık; kod başlamadı)

## Bağlam
Faz 3 sorusu tek: **kayıtlı veri üzerinde tanımlanan piyasa durumlarından herhangi biri, maliyetleri aşan ileriye dönük beklenti üretiyor mu?** Hayırsa proje durur. Bu yüzden metodoloji, "evet" çıkarmaya değil, yanlış "evet"i engellemeye göre kurulur.

## Kararlar

1. **Veri kaynağı:** yalnızca Faz 1 kaydı; Faz 2 çekirdeğinin ürettiği 1 dk `BarClosed` dizisi + bar kapanış anındaki bookTicker spread + markPrice funding oranı. Dış veri, kline REST geçmişi yok (look-ahead ve format farkı riski).
2. **Zaman disiplini (look-ahead yasağı):** bar `t`'nin feature'ları yalnızca `T ≤ t.end_ms` olan verilerden hesaplanır. Doğrulama testi: veri `t`'de kesilip yeniden hesaplanınca feature değerleri bit-eşit kalır ("kesme testi"). Rolling pencereler geçmişe bakar, merkezlenmez.
3. **Durum sayısı ≤ 5**, eşikler mutlak değil: sembol başına rolling persentil (pencere `W` bar). Ağırlıklı skorlama yok; her durum en fazla 2 koşulun AND'i.
4. **Ufuklar:** 1, 5, 15, 60 dk (Faz 0 kuralı: ufuk ≥ 10 × ~1 s gecikme → ≥ 10 s; en kısa ufuk 1 dk).
5. **Giriş/çıkış fiyatı (muhafazakâr):** giriş = bar `t+1`'in ilk işlem fiyatı + yarım spread (taker), çıkış = bar `t+h` kapanışı − yarım spread (taker). `trigger_price_source` ve `execution_price_estimate` ayrımı burada başlar: durum tespiti bar kapanışıyla, dolum tahmini bir sonraki işlemle.
6. **Maliyet her hücrede:** komisyon (taker/taker ana senaryo, maker/taker duyarlılık), spread (ölçülen), slippage (80 USDT notional için ölçülen ≈ 0; yine de defterden), funding (ufuk funding zamanını keserse o anki `r` ile). Maliyetsiz sonuç raporlanmaz.
7. **Örnekleme:** ufuk `h` için örtüşmeyen örnekler (her `h` barda bir) — bağımlı örneklerin sahte anlamlılığını önler.
8. **Çoklu test disiplini:** 5 durum × 4 ufuk × 2 yön = 40 hücre. Karar hücresi için: (a) zaman bazlı ayrım — ilk %70 "keşif", son %30 "doğrulama"; (b) doğrulama bölümünde bootstrap %95 güven aralığının alt sınırı > 0; (c) `n ≥ 100` (örtüşmeyen); (d) keşifte anlamlı çıkmayan hücre doğrulamada bakılmaz (p-hacking yok).
9. **Rastlantı:** bootstrap seed'i config'de (`research.seed`). Aynı kayıt + aynı config → aynı rapor (Rule Zero araştırmaya da uygulanır).
10. **Karar kuralı (DUR kapısı):** en az bir hücre (a)–(d)'yi sağlıyorsa Faz 4'e geçilir ve o hücreler Faz 4/6'nın odağıdır. Hiçbiri sağlamıyorsa **kod yazımı durur**, rapor proje sahibine sunulur.
11. **Veri gereksinimi (ölçülmüş hızdan):** 10 sembol × 1 dk bar = 14.400 bar/gün. 60 dk ufkunda örtüşmeyen örnek 240/gün; 5 duruma dağılınca ~50/durum/gün. `n ≥ 100` için **≥ 3 gün kayıt** (60 dk ufku), ≤ 15 dk ufukları için 1 gün yeter. Ön rapor 24 saatlik kayıtla, nihai rapor ≥ 3 günle.

## Reddedilenler
- Kline REST geçmişiyle veri artırmak: replay ile aynı zaman damgası semantiği değil; look-ahead ve dolum tahmini tutarsız.
- Tek büyük örneklem (örtüşen pencereler): n şişer, anlamlılık sahte.
- Eşikleri "en iyi sonucu veren" değerlerde sabitlemek: overfit; persentil kuralı sabit kalır, yalnızca `W` ve persentil seviyeleri config'dedir ve keşif/doğrulama ayrımı onları da kapsar.

## Sonuçlar
- Faz 6 Market State Engine, buradaki durum tanımlarını **değiştirmeden** çekirdeğe taşır.
- Araştırma kodu `fbot/research/` altında saf; I/O yalnızca `scripts/`.
