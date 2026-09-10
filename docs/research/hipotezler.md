# Faz 3 — durum adayları ve hipotezler

Tarih: 2026-09-10 (hazırlık). Tüm eşikler sembol başına rolling persentildir; sayısal değerler config'dedir ve ölçüm öncesi "bilinmiyor"dur.

## Feature seti (bar kapanışında, geçmişe bakan)

| Ad | Tanım | Kaynak |
|---|---|---|
| `ret_N` | N barlık log getiri (N ∈ {5, 15}) | bar close |
| `rv_N` | N barlık gerçekleşen volatilite: 1 dk log getirilerin kareleri toplamının kökü | bar close |
| `vol_ratio` | son bar hacmi / önceki W bar ortalama hacmi | bar volume |
| `imb_N` | N barda alıcı-agresif hacim − satıcı-agresif hacim, toplam hacme oranı (`m` alanı) | aggTrade `m` |
| `spread_bps` | bar kapanış anındaki bookTicker spread | bookTicker |
| `basis_bps` | (mark − index) / index | markPrice `p`, `i` |

Persentil: her feature için sembol başına son W barın rolling persentili (`pct(x)` ∈ [0,1]). W ve persentil eşikleri (`p_lo`, `p_hi`) config.

## Durum adayları (en fazla 5; S0 varsayılan)

| Durum | Kural (AND, en fazla 2 koşul) | Sezgi |
|---|---|---|
| S0 NÖTR | diğerlerinin hiçbiri | işlem yok |
| S1 TREND_UP | `pct(ret_15) > p_hi` AND `pct(rv_15)` ∈ [p_lo, p_hi] | düzenli yükseliş, aşırı genişleme yok |
| S2 TREND_DOWN | `pct(ret_15) < p_lo` AND `pct(rv_15)` ∈ [p_lo, p_hi] | simetrik |
| S3 SIKIŞMA | `pct(rv_15) < p_lo` AND `pct(spread_bps) < p_hi` | düşük vol, likit defter; kırılım öncesi |
| S4 AŞIRI_GENİŞLEME | `pct(rv_5) > p_hi` AND `pct(vol_ratio) > p_hi` | ani hareket + hacim; tükenme ya da devam |

Yön: S1 long, S2 short; S3 ve S4 için iki yön de test edilir (S3 kırılım yönü `imb_5` işaretiyle, S4 ters yön = tükenme hipotezi, aynı yön = devam hipotezi).

## Yanlışlanabilir hipotezler

H1. S1 sonrası 15 ve 60 dk long net getiri beklentisi > 0 (maliyet dahil).
H2. S2 sonrası 15 ve 60 dk short net getiri beklentisi > 0.
H3. S3 sonrası `imb_5` yönünde 5 ve 15 dk net beklenti > 0.
H4a. S4 sonrası ters yönde 5 dk net beklenti > 0 (tükenme).
H4b. S4 sonrası aynı yönde 15 dk net beklenti > 0 (devam). H4a ve H4b birlikte doğru olamaz; hangisi doğrulanırsa o kalır.
H0. Hiçbiri doğrulama bölümünde ADR 0008 §8 koşullarını sağlamıyorsa proje durur.

## Rapor şablonu (hücre başına)

`durum | ufuk | yön | n (örtüşmeyen) | ort. brüt % | ort. maliyet % | ort. net % | medyan net | kazanma oranı | %95 CI alt/üst (bootstrap, seed) | keşif/doğrulama`

Ek: durum başına süre dağılımı, geçiş matrisi, sembol başına kırılım, spread ve funding katkısı.

## Veri durumu

Kayıt 2026-09-10 08:00 UTC'de başladı. Ön rapor: ≥ 24 saat. Nihai: ≥ 3 gün (ADR 0008 §11).
