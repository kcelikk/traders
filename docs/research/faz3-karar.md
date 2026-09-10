# Faz 3 karar dokümanı — DUR kapısı

Tarih: 2026-09-10 · Rapor: `docs/research/rapor-hist-30d.md` (hash `a693aa0742076410`), tarama: `docs/research/tarama-hist-30d.md`. Metodoloji ADR 0008, veri kaynağı ADR 0009.

## Soru
Tanımlanan 5 piyasa durumundan herhangi biri, 1/5/15/60 dk ufuklarında, maliyet düşüldükten sonra pozitif beklenti üretiyor mu?

## Cevap: **Hayır.** ADR 0008 §10 gereği kod yazımı durur.

## Kanıt

Veri: 10 sembol (bugünün TOP 10'u), 2026-08-09 – 2026-09-09, 460.341 bar (1 dk), Binance geçmiş aggTrades'ten Faz 2 çekirdeğiyle üretildi. Keşif %70 / doğrulama %30 zaman bazlı. 4 durum × 4 ufuk × yönler = 48 hücre × 2 maliyet senaryosu.

| Bulgu | Değer |
|---|---|
| Doğrulamayı geçen hücre (taker/taker) | **0 / 48** |
| Doğrulamayı geçen hücre (maker/taker) | **0 / 48** |
| Keşif aşamasını geçen hücre (herhangi bir senaryo) | 0 |
| Brüt getiri aralığı, 1–15 dk, tüm hücreler | −0.044 % … +0.025 % (maliyet 0.100 %) |
| Brüt getiri aralığı, 60 dk | short: −0.046 … −0.128 % ; long: +0.014 … +0.110 % |
| Maker/taker senaryosunda doğrulamada net > 0 hücreler | S1 long 60 dk +0.031 % (CI −0.030…0.090), S4 rev long 60 dk +0.039 % (CI −0.051…0.127) — anlamsız, keşifte de elenmiş |
| Parametre taraması (9 nokta, yalnızca keşif) | en iyi hücre net +0.013 % (S4 rev long 60 dk, p=0.1/0.9); diğerleri negatif |

Yorum:
1. **1–15 dk ufuklarında durumlar yön bilgisi taşımıyor.** Brüt getiri maliyetten bağımsız olarak sıfıra yakın; maliyet sıfır olsaydı bile beklenti pratikte sıfırdır.
2. **60 dk long hücrelerindeki brüt pozitiflik dönem sürüklenmesidir:** tüm long'lar pozitif, tüm short'lar negatif; durumdan bağımsız. Yön seçici olmayan bir sinyal, durum tanımının değerini göstermez.
3. Maker giriş (%0.07 maliyet) sonucu değiştirmiyor; maker/maker (%0.04) bile 60 dk long'ları ancak sıfır civarına taşır ve dolum varsayımı gerektirir.

## Sınırlar (sonucu lehte değiştirebilecek olanlar dahil)
- 32 gün, tek rejim (yukarı sürüklenme). Daha uzun dönem farklı rejimler içerir; ancak **aynı hipotezleri daha fazla veriyle yeniden test etmek, doğrulama zaten başarısızken, sonuç arama (p-hacking) olur**. Yalnızca önceden kayıtlı bir "tekrar" olarak yapılabilir.
- Evren bugünün TOP 10'u (hayatta kalma yanlılığı; lehte yanlılık yönünde, aleyhte değil).
- Spread sabit (Faz 1 kaydı medyanı); funding gerçekleşen oranla (küçük look-ahead, ≤ 0.01 %). İkisi de sonucu değiştirecek büyüklükte değil.
- Komisyon oranı VIP0, doğrulanmadı. Daha düşük kademe maliyeti düşürür ama brüt sıfır civarında kaldığı için karar değişmez.

## Seçenekler (proje sahibi kararı)

**A. DUR.** Kural bu. Repo, kayıt ve araçlar durur; recorder istenirse kapatılır.

**B. Yeni hipotez döngüsü (ADR 0008'in izin verdiği tek devam yolu).** Koşullar: hipotezler veriye bakılmadan **önceden yazılır**, doğrulama **henüz görülmemiş** veride yapılır (2026-09-10 sonrası günler + kayıt), aynı karar kuralı. Aday yönler, hepsi sezgi ve hiçbiri kâr varsayımı değil:
   - Daha uzun ufuklar (4 sa, 24 sa): maliyetin oransal payı küçülür; funding ve gecelik risk büyür.
   - Bu fazda hiç kullanılmayan veri: `forceOrder` (likidasyon kaskadları), `depth` (defter dengesizliği), premium index / funding uçları. Faz 1 kaydında hepsi var; geçmişte `bookDepth`/`metrics` dosyaları var.
   - Yön seçici olmayan yapılar (beta-nötr sembol çiftleri) — Faz 5'teki beta hesabıyla.
   - Bir döngünün maliyeti: hipotez dokümanı + feature kodu + 1 rapor; günler, haftalar değil.

**C. Aynı hipotezleri daha uzun geçmişle tekrar.** Yalnızca "tekrar" olarak, sonucun değişmesi beklenmeden; ADR 0008'e göre karar hücresi üretemez.

## Öneri
Kural gereği **A**; devam istiyorsan **B**, yeni hipotez dokümanı senin onayınla yazılır ve doğrulama verisi bugünden sonra biriken günler olur. C tek başına önerilmez.
