# Faz 6 tasarım notu — Market State Engine ve Decision Engine (giriş)

Tarih: 2026-09-10 · Durum: tasarım notu, kod yok. Faz 6 yalnızca Faz 3 DUR kapısı geçilir ve Faz 4–5 kapanırsa başlar. Durum tanımları Faz 3'ten **değiştirilmeden** taşınır.

## 1. İlke

- Giriş ikincil önceliktir; amaç fiyat tahmini değil, Faz 3'te maliyet üstü beklenti göstermiş **(durum, ufuk, yön)** hücrelerinde pozisyon açmaktır. Başka hiçbir hücrede giriş yoktur.
- **v1'de ağırlıklı skorlama yok.** Karar = en fazla 3 sert koşulun AND'i. Her ağırlık serbest parametredir ve overfit üretir.
- Her karar açıklanabilir: hangi durum, hangi feature değerleri, hangi hücre, hangi config hash, hangi git SHA, correlation id.

## 2. Market State Engine (çekirdek, saf)

- Faz 3 `fbot/research/states.py` kuralları ve `features.py` hesapları çekirdeğe taşınır (`fbot/core/state_engine.py`), fonksiyonlar aynı kalır; test: research ve core aynı bar dizisinde aynı etiketleri üretir (bit-eşit).
- Girdi: `BarClosed` dizisi + bar kapanış anındaki spread. Çıktı: `StateChanged(symbol, from, to, confidence, evidence, t)`.
- **Confidence** skor değildir: durumu tanımlayan koşulların persentil eşiğinden uzaklığının minimumudur (örn. S1 için `min(pct_ret_long − p_hi, band mesafesi)`); yalnızca raporlama ve Faz 7 analizi içindir, karara girmez.
- **Evidence:** koşula giren feature değerleri ve persentilleri; **karşıt kanıt:** koşulu bozmaya en yakın feature. Her geçişte süre ve zaman damgası kaydedilir (prompt 5.5).
- Durum sayısı 5'te sabit. Yeni durum önerisi = eski bir durumun yerine ve yeni bir Faz 3 döngüsü.

## 3. Decision Engine (çekirdek, saf)

`decide(symbol_state, market_view, allowed_cells, cfg, now) -> EntryIntent | None`

Sert koşullar (hepsi AND, en fazla 3):

| # | Koşul | Kaynak |
|---|---|---|
| D1 | `(state, dir)` Faz 3'te doğrulanmış hücre listesinde (`allowed_cells`, config; rapor hash'i ile birlikte) | ADR 0008 §10 |
| D2 | Durum bu bar kapanışında **yeni** girildi (`StateChanged` aynı bar) ya da durum süresi ≤ `max_state_age_bars` | girişler durumun başında; geç giriş yasak |
| D3 | Yürütme uygunluğu: spread ≤ hücrenin araştırmadaki ortalama spread'i × `spread_mult`, bayatlık yok | araştırma varsayımlarının dışına çıkma |

`EntryIntent`: sembol, yön, notional (80 USDT, ADR 0004), hedef ufuk `h` (hücreden), SL/TP mesafeleri (Faz 3/4 replay'inden; `null` ise **intent üretilmez**), correlation id, açıklama (D1–D3 değerleri). Risk Engine (Faz 5) veto/RESIZE uygular; Decision Engine Risk'i beklemek zorundadır (prompt 5.2), Position Monitor beklemez.

## 4. Giriş emri mekaniği (I/O kenarı, Faz 9)

- Tercih: maker giriş (`GTX` ya da `priceMatch=QUEUE`), çünkü maliyet %0.10 → %0.07 (unit economics). Dolmazsa `entry_timeout` sonunda iptal; taker'a dönüş **config** (varsayılan hayır: dolmayan giriş kaçırılan giriştir, pahalı değildir).
- Giriş emri için `countdownCancelAll` düşünülebilir (yalnızca giriş; koruma emirlerine asla) — algo etkileşimi Faz 9'da test edilmeden kullanılmaz.
- `newClientOrderId` deterministik: `e{symbol}{bar_end_ms}{dir}`; aynı bar için ikinci intent üretilemez (idempotent).
- Fill → Faz 4 PROTECTING.

## 5. Evren ve zamanlama

- TOP 10 günlük 00:00 UTC yenileme (ADR 0004): yeni sembol `2W` ısınma bekler; çıkan sembolde D1 kapanır, açık pozisyon Faz 4 kurallarıyla yönetilir.
- Funding anına `funding_guard_ms` kala giriş yok (ufuk funding'i kesecekse maliyet araştırmadakinden sapar) — config.

## 6. Kabul kriterleri (taslak)

1. Core state engine ≡ research states (bit-eşit test).
2. Karar yalnızca `allowed_cells` içinde; boş listeyle sıfır intent (test).
3. Her intent açıklama taşır; replay'de aynı kayıt aynı intent dizisi.
4. Replay: girişler + Faz 4 çıkışlar + Faz 5 vetolar birlikte, maliyet dahil net beklenti > 0 ve Faz 3 hücre sonuçlarıyla tutarlı (sapma açıklanır).

## 7. Proje sahibine sorular

1. Dolmayan maker girişte taker'a dönüş istiyor musun? (Öneri: hayır.)
2. `max_state_age_bars`: durum başladıktan kaç bar sonra giriş geç sayılsın? (Faz 3 verisinden öneri gelecek.)

## 8. Bu notta olmayanlar

- Hangi hücrelerin geçeceği; Faz 3 sonucu.
- SL/TP mesafeleri; Faz 3/4.
- Skorlama/model: v1 dışı; ancak etiketli veri + walk-forward sonra, ayrı fazda.
