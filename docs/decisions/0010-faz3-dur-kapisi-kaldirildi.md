# ADR 0010 — Faz 3 DUR kapısı kaldırıldı

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi kararı: "bu kuralı sil")

## Bağlam
Başlangıç promptu (BÖLÜM 14, Faz 3) ve CLAUDE.md, offline araştırma negatif çıkarsa projenin durmasını ve kod yazılmamasını istiyordu. 30 günlük araştırma (docs/research/faz3-karar.md) 5 durum tanımının hiçbirinde maliyet üstü beklenti göstermedi. Proje sahibi kuralı gerçekçi bulmadı: kısıtlı bir örneklemden "piyasada kazanılabilir durum yok" kesinliği türetilemez; ölçüm yalnızca test edilen tanımlar hakkında konuşur.

## Karar
1. Faz 3 bir **kapı değil, bilgilendirici araştırma adımıdır**. Sonucu negatif de olsa Faz 4'e geçilir.
2. Faz 3'ün çıktıları (hücre tablosu, maliyet baskınlığı bulgusu, sürüklenme etkisi) Faz 4–6 tasarımına **girdi** olarak kullanılır; araştırma döngüsü paralelde sürer ve yeni hipotezler aynı yöntemle (ADR 0008 §2–9: look-ahead yok, keşif/doğrulama, örtüşmeyen örnekleme, bootstrap) raporlanır. ADR 0008 §10 (proje durur) **geçersizdir**.
3. "Kârlılık gösterilmedi" ibaresi, ölçülmüş bir avantaj bulunana kadar her rapor ve teslimde yer alır. Bu, kuralın yerine geçen tek şeydir: sonuç saklanmaz, ama kod yazımını engellemez.
4. Gerçek para riski Faz 10'a kadar sıfırdır; paper ve testnet fazları avantajın ölçüldüğü yerdir.

## Sonuçlar
- CLAUDE.md "Faz 3 bir dur kapısıdır" paragrafı kaldırıldı; YASAKLAR'daki "faz atlama" kuralı korunur (sıra aynı, kapı yok).
- Faz 4 başlar: strateji-bağımsız altyapı (pozisyon durum makinesi, koruma emirleri, tick olayı, yedek stop, zaman aşımı).
- Faz 6 giriş mantığı, mevcut 5 durumla yazılabilir; beklentisi Faz 3 raporundaki değerlerdir ve paper'da ölçülür.
