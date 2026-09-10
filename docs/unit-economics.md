# Unit economics — Faz 0 (prompt BÖLÜM 6.3)

Tarih: 2026-09-10. Hesaplayıcı: `scripts/unit_economics.py` (çekirdek `scripts/unit_economics_core.py`, 10 test).
Ham veri: `data/unit-economics/` (funding 500 kayıt/sembol ≈ 166 gün, 3 defter anlık görüntüsü/sembol, exchangeInfo).
Tam tablolar: `docs/unit-economics.generated.md`.

## Girdi kaynakları ve güven durumu

| Girdi | Değer | Kaynak | Güven |
|---|---|---|---|
| Komisyon VIP0 maker / taker | %0.02 / %0.05 | Üçüncü taraf siteler; resmi ücret sayfası ve FAQ login'siz tabloyu render etmiyor | **DOĞRULANMADI** — hesaptan `GET /fapi/v1/commissionRate` ile düzeltilecek |
| BNB indirimi | %10 | Resmi FAQ 360033544231 (güncelleme 2026-05-01): "10% discount … when they use BNB" | doğrulandı |
| Funding aralığı BTCUSDT, ETHUSDT | 8 saat | `GET /fapi/v1/fundingInfo` | ölçüldü |
| Funding ort. mutlak oran | BTC %0.0049 / ETH %0.0045 per 8 saat | `GET /fapi/v1/fundingRate` son 500 kayıt | ölçüldü, 166 gün |
| Spread | BTC 0.01 bps, ETH 0.13 bps | 3 anlık görüntü, 2026-09-10 ~07:35 UTC | ölçüldü, **tek an**, sakin piyasa |
| Slippage 1.000 USDT | ≈ 0 bps (ilk seviyede doluyor) | `GET /fapi/v1/depth` limit=100 | ölçüldü, **tek an**; RPI emirleri defterde görünmez |
| Min notional | BTC 50 USDT, ETH 20 USDT | exchangeInfo `MIN_NOTIONAL` | ölçüldü |
| Tick / step | BTC 0.10 / 0.001, ETH 0.01 / 0.001 | exchangeInfo | ölçüldü |
| Sermaye, tutma süresi, günlük işlem, hedef hareket, R:R | — | proje sahibi | **BİLİNMİYOR** |

## BÖLÜM 6.3 tablosu

| Kalem | Değer |
|---|---|
| Hedef tutma süresi | **?** (proje sahibi / Faz 3 verisi). Duyarlılık: 5 dk – 24 sa aşağıda |
| Beklenen günlük işlem sayısı | **?** (proje sahibi / Faz 3 verisi) |
| İşlem başına ortalama hedef hareket (%) | **?** (Faz 3'te durum başına ileriye dönük getiri dağılımından) |
| Gidiş-dönüş komisyon (%) | taker/taker **0.100** · maker/taker 0.070 · maker/maker 0.040 · BNB ile ×0.9 (VIP0, doğrulanmadı) |
| Ortalama funding maliyeti (%) | 30 dk: 0.0003 · 8 sa: 0.005 · 24 sa: 0.015 (ort. mutlak, aleyhte varsayım) |
| Tahmini slippage (%) | ≈ 0.000 (1.000 USDT, sakin an) — **volatil anlarda ölçülmedi** |
| **Başabaş için gereken minimum hareket (%)** | taker/taker 30 dk: **0.100** · maker/maker 30 dk: **0.040** · taker/taker +BNB: 0.090 |
| **Başabaş kazanma oranı** (taker/taker, 30 dk, maliyet %0.10) | hedef %0.3: R:R1 66.7% / R:R2 55.7% · hedef %0.5: 60.0% / 46.7% · hedef %1.0: 55.0% / 40.0% · hedef %2.0: 52.5% / 36.7% |

Maliyetsiz klasik başabaş: R:R1 50%, R:R1.5 40%, R:R2 33.3%. Maliyetin etkisi hedef hareket küçüldükçe büyür: %0.3 hedefte R:R1 için gereken kazanma oranı 50'den 66.7'ye çıkar.

## Yorum

1. **Maliyet komisyon baskın.** 8 saatin altındaki tutmalarda funding ve slippage (sakin piyasada) ihmal edilebilir; gidiş-dönüş maliyetin %95'i komisyondur. Taker/taker ile her işlem notional'ın %0.10'unu yakar.
2. **Kaldıraç maliyeti büyütür.** Maliyet notional üzerinden hesaplanır; 10x kaldıraçta bir işlem teminatın %1'ini, 5x'te %0.5'ini yakar. Günde 20 taker/taker işlem 10x'te teminatın %20'sine denk gelir. BÖLÜM 6.4 alarmının gerekçesi budur.
3. **Maker girişi tek başına maliyeti %60 düşürür** (0.10 → 0.04 maker/maker; 0.07 maker/taker). Giriş emirlerinde maker (GTX / `priceMatch QUEUE`) tercihi, çıkışta koruma zorunluysa taker. Bu, Faz 4/6 tasarımına girdi.
4. **Hedef hareket alt sınırı.** Maliyet %0.10 iken %0.3'ün altındaki hedefler pratikte kazanma oranı >%65 gerektirir; Faz 3 araştırması hedef hareketi ≥ %0.5 olan durumlara odaklanmalı (gerekçe: tabloda %0.5 hedefte R:R1.5 ile başabaş 52%).
5. **Slippage ölçümü yetersiz.** Üç sakin anlık görüntü, volatil anlardaki derinliği temsil etmez. Faz 1 recorder depth akışını kaydettikten sonra slippage dağılımı yeniden hesaplanacak; o zamana kadar config'e sabit slippage yazılmaz, "bilinmiyor" kalır.

## Kapı değerlendirmesi

Tablo, proje sahibinden gelecek üç girdi (tutma süresi, işlem sayısı, hedef hareket) olmadan tek satıra indirgenemez. Duyarlılık tablosu şunu gösteriyor: **hedef hareket ≥ %0.5 ve maker giriş** koşulunda başabaş kazanma oranı klasik değerin 5–7 puan üstünde kalıyor ve bu aşılabilir bir eşik. **Hedef hareket < %0.3 ve taker/taker** koşulunda kapı tutmuyor. Hangi bölgede olduğumuz Faz 3'te veriyle belirlenecek; Faz 0 kapısı için karar proje sahibinin.
