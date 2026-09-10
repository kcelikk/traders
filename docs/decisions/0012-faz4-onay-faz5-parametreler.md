# ADR 0012 — Faz 4 onayı ve Faz 4/5 açık kararları (öneriler uygulanır)

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi: "Faz 4 onay, önerilerini uygula")

| Konu | Karar |
|---|---|
| SL/TP tetik kaynağı | `workingType = MARK_PRICE`, `priceProtect = true` (config, sembol başına değiştirilebilir) |
| Kısmi azaltma (R4) | filtre izin verdiğinde çalışır; BTC gibi minimumda açılan pozisyonlarda pas geçilir, notional artırılmaz |
| Durum bozulması çıkışı (R2) | reduceOnly MARKET (kesinlik > maliyet); `priceMatch` LIMIT varyantı Faz 7 ölçümünden sonra |
| Günlük net zarar limiti | kill switch tetikleyicisi **evet**; değer proje sahibinden gelene kadar `null` (kapalı) — config `daily_loss_limit_pct` |
| Brüt maruziyet tavanı | 400 USDT (80 × 5) |
| BTC-beta tavanı | `null` (beta dağılımı ölçülene kadar kapalı) |
| Zararlı çıkış sonrası cooldown | evet; `cooldown_loss_ms` başlangıç `null`, paper'da ölçülerek belirlenir |
| Faz 4 | **KAPANDI** |

Sayısal değerlerin tamamı config'de ve ölçülene kadar `null`; hiçbiri kod içinde sabit değil.
