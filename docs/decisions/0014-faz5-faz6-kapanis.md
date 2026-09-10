# ADR 0014 — Faz 5 ve Faz 6 kapanışı; risk parametreleri

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi: "5,6 onay, 2 ve 4 kapalı kalsın, 3 için beta dağılımını çıkar")

## Kapanan fazlar
- **Faz 5 (Risk Engine):** K1–K18 saf `assess`, runaway dedektörü, kalıcı kill switch (atomik dosya + geçmiş), mutabakat karşılaştırması, çekirdeğe bağlı giriş zinciri. 
- **Faz 6 (Giriş mantığı):** Market State Engine çekirdekte (araştırma koduyla bit-eşit test), Decision Engine D1–D3 (ağırlıklı skorlama yok), açıklanabilir intent, fail-closed sl/tp.

## Risk parametreleri (proje sahibi kararı)

| Parametre | Karar | Not |
|---|---|---|
| Günlük net zarar limiti (`daily_loss_limit_pct`) | **kapalı** (`null`) | Kill switch tetikleyicisi olarak devrede değil; elle tetikleme ve diğer tetikleyiciler (418, mutabakat uyuşmazlığı, runaway, korumasız pozisyon) açık kalır |
| Zararlı çıkış sonrası bekleme (`cooldown_loss_ms`) | **kapalı** (`null`) | Ölçüm yok; paper verisi biriktikçe yeniden değerlendirilir |
| BTC-beta tavanı (`beta_cap_usdt`) | **ölçüldü, değer proje sahibinden bekleniyor** | Ölçüm aşağıda |

## BTC-beta ölçümü (30 gün, 46.049 bar, 10 sembol, 240 barlık pencere)

`beta = Cov(r_alt, r_btc) / Var(r_btc)`, 1 dk log getiri. Tam tablo: `docs/research/beta-dagilimi.md`.

- Medyan beta'lar 0.69 (BNB) ile 1.58 (ZEC) arasında; ETH 1.07, SOL 1.25, XRP 1.33, NEAR 1.44.
- p95 beta'lar 1.17 – 2.86; tek tek maksimumlar 6.28'e kadar çıkıyor.
- **80 USDT'lik bir ZEC pozisyonu, BTC cinsinden 126 USDT'lik maruziyet demek** (medyan beta 1.58).
- 5 eşzamanlı pozisyon (400 USDT brüt) hepsi aynı yönde ve yüksek beta'lı sembollerde olsaydı net BTC-beta maruziyeti **≈ 958 USDT**, yani brütün 2.4 katı. Rastgele 5 sembolde ≈ 765 USDT.

**Yorum:** "5 farklı altcoin = tek büyük BTC pozisyonu" varsayımı ölçümle doğrulandı ve altcoin'lerde etki brütten büyük. `beta_cap_usdt` seçimi:
- 400 USDT (brüt tavana eşit) → aynı yönde 2–3 pozisyondan sonrası fiilen engellenir. Sıkı.
- 750 USDT (ölçülen ortalama senaryo) → 5 pozisyona izin verir, aşırı yığılmayı keser. Orta.
- 1000+ USDT → K9 pratikte hiç devreye girmez.

Karar proje sahibinde; verilene kadar `beta_cap_usdt = null` (K9 kapalı) kalır ve bu her risk raporunda belirtilir.

## Sonuçlar
- Faz 7 (paper) tek açık iş; Faz 9 (testnet) proje sahibi onayıyla başlıyor.
- Kapalı bırakılan üç parametre config'de `null` durur ve konsolda "kapalı" olarak görünür; sessizce varsayılan değer atanmaz.
