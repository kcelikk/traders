# Faz 10 tasarım notu — küçük sermaye ile canlı

Tarih: 2026-09-10 · Durum: tasarım notu, kod yok. Yalnızca proje sahibinin **açık ve yazılı** onayıyla; varsayılan mod paper kalır.

## 1. Etkinleştirme zinciri (hepsi aynı anda sağlanmalı, biri eksikse paper)
1. Config `mode = "live"` **ve** ortam değişkeni `FBOT_LIVE_ARMED=<onay tarihi>` **ve** kill switch kapalı **ve** mutabakat OK.
2. Anahtar izin kontrolü: çekim kapalı, IP whitelist açık; aksi halde process çıkar.
3. Hesap ayarları doğrulama: one-way mode, sembol başına kaldıraç (BTC/ETH 10x, diğer 5x), margin tipi (proje sahibi kararı: isolated önerisi), multi-assets kapalı.
4. Canlı öncesi "kuru" döngü: 1 sembolde en küçük geçerli notional ile giriş → SL/TP yerleşimi → elle iptal; borsa tarafı korumanın gerçekten yerleştiği ekranda görülür.
5. Kill switch tatbikatı: `make kill` → giriş reddi; `make kill-reset` → devam.

## 2. Guardrail'ler (sert, config; değerler proje sahibinden)
| Guardrail | Etki |
|---|---|
| Sermaye tavanı (`live_capital_cap_usdt`) | toplam teminat bunu aşamaz; aşan intent REJECT |
| Günlük net zarar limiti | kill switch (Faz 5 sorusu) |
| Sembol evreni | başlangıçta **1 sembol** (öneri BTCUSDT: en likit, min notional 78 USDT), sonra kademeli |
| İşlem büyüklüğü | 80 USDT notional (ADR 0004), değiştirilmez |
| Eşzamanlı pozisyon | 1 ile başla, 5 tavan |
| Canlı süresi | ilk 1 hafta "gözetimli": proje sahibi günlük rapor onaylamadan devam yok |

## 3. Mutabakat ve muhasebe
- Günlük: `GET /fapi/v1/income` (REALIZED_PNL, COMMISSION, FUNDING_FEE) ile iç muhasebe karşılaştırması; sapma > eşik → alarm + trading kilidi.
- Her işlem `config_version`, `git_sha`, `correlation_id` taşır; canlı ile paper aynı kod yolundan geçer (yalnızca adapter farklı).
- Paper vs canlı karşılaştırma: fill fiyatı, slippage, gecikme, ret oranı; Faz 7 fill modeli buna göre düzeltilir.

## 4. Geri dönüş (rollback) kuralları
- Kill switch tetiği, mutabakat uyuşmazlığı, 418, koruma ACK gecikmesi, günlük zarar limiti → otomatik paper'a dönüş **değil**: yeni giriş durur, açık pozisyonlar Faz 4 kurallarıyla kapatılır, sonra proje sahibi kararı.
- Kod değişikliği canlıdayken yok: her deploy önce paper'da en az 1 gün.

## 5. Kabul (bu fazın "kapısı" yoktur; sürekli işletmedir)
- Haftalık rapor: BÖLÜM 12 metrikleri + maliyet sürüklenmesi + paper/canlı sapması.
- Kârlılık iddiası yalnızca income kayıtlarına dayanır; iç hesap raporlanmaz.

## 6. Sorular
1. Sermaye tavanı ve günlük zarar limiti değerleri.
2. Margin tipi: isolated mı cross mu?
3. İlk sembol BTCUSDT kabul mü?

## 7. Olmayanlar
Hiçbir sayısal değer; kârlılık beklentisi; süre taahhüdü.
