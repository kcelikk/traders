# Dokümantasyon Kuralları İnceleme Raporu

Tarih: 2026-09-10

Kapsam: Proje dokümantasyonunda geliştirmeyi yavaşlatabilecek, gereğinden katı veya birbiriyle çelişen kurallar. Bulgular belge incelemesine dayanır; önerilerin süre kazancı ölçülmemiştir. Bu rapor mevcut kuralları değiştirmez veya onaylanmış kararların yerine geçmez.

## Genel Değerlendirme

En belirgin sorun, eski ve yeni kuralların birlikte yürürlükteymiş gibi görünmesidir. Bazı kısıtlar ADR'lerle kaldırıldığı hâlde tasarım notlarında zorunlu görünmektedir. Öncelik, belge çelişkilerinin giderilmesi ve teknik kabul ile strateji başarısının ayrılması olmalıdır.

İnceleme anındaki `docs/PHASE.md`, Faz 5 ve 6'yı “teslim edildi”, Faz 8'i “kısmen başladı” olarak gösterir. “Teslim edildi” ifadesi, kabul kriterlerinin bağımsız olarak doğrulandığı anlamına gelmez. **Kârlılık gösterilmedi.**

## 1. Geçersizleşmiş Kapıların Zorunlu Görünmesi

**Öncelik: Yüksek — doğrulanmış belge çelişkisi.**

**Kanıt:** [ADR 0011](decisions/0011-gerceklik-duzeltmeleri.md), testnet için iki hafta şartını test planı ve en az 100 emir döngüsüyle değiştirir; paper için dört haftayı hedef yapar; model yasağını doğrulama şartına dönüştürür. Buna rağmen [Faz 7 tasarımı](design/faz7-paper-trading.md) dört haftayı kilitli şart, [Faz 6 tasarımı](design/faz6-giris-mantigi.md) kaldırılmış DUR kapısını başlangıç koşulu gösterir. [Faz tablosunda](PHASE.md) eski süreler de durmaktadır.

**Etki:** Gereksiz bekleme ve karara bağlanmış konular için yeniden onay isteme riski.

**Öneri:** Geçersiz maddeleri ilgili ADR'ye bağlantıyla işaretleyin; güncel kabul kriterlerini tek yerde tutun. Tarihsel karar kayıtlarını silmeyin.

## 2. Aktif Faz Dışında Çalışma Yasağı

**Öncelik: Orta — kapsamı daraltılması önerilen kural.**

**Kanıt:** [CLAUDE.md, Oturum Başı Kontrol Listesi](../CLAUDE.md) “Aktif fazın dışında iş yapma” der. Faz tablosunda ise Faz 8 kısmen başlamıştır.

**Etki:** Mevcut fazı doğrulamak için gereken paper akışı veya gözlem araçları da engellenebilir.

**Öneri:** Fazlar öncelik ve kabul sırasını belirlesin; mevcut fazın doğrulanmasını destekleyen bağımlı çalışmalar yapılabilsin. Canlıya geçiş kapıları korunsun.

## 3. Her Belirsizlikte Durma Zorunluluğu

**Öncelik: Orta — gereksiz onay trafiği riski.**

**Kanıt:** [CLAUDE.md, Mutlak Kurallar](../CLAUDE.md), belirsizlikte durup kullanıcı cevabını beklemeyi zorunlu tutar.

**Etki:** Dosya adı gibi geri alınabilir tercihler ile sermaye limiti gibi önemli kararlar aynı süreçten geçebilir.

**Öneri:** Sermaye, canlı emir, veri silme ve kapsam değişikliği sorulsun. Uygulama yetkisi verilmiş işlerde geri alınabilir teknik tercihler gerekçesi belirtilerek çözülebilsin. Ajanın mevcut yalnızca inceleme ve raporlama rolü bundan ayrı tutulmalıdır.

## 4. Teknik Kabulün Pozitif Getiriye Bağlanması

**Öncelik: Yüksek — geliştirme akışını kilitleme riski.**

**Kanıt:** [Faz 6 kabul kriterleri](design/faz6-giris-mantigi.md) pozitif net beklenti ister. [Faz tablosuna](PHASE.md) göre `allowed_cells` boştur; boş listeyle sıfır intent üretilmesi de kabul kriteridir.

**Etki:** Emir üretmeyen koşuyla pozitif işlem beklentisi gösterilemez; teknik altyapının paper doğrulaması gecikebilir.

**Öneri:** Motor doğruluğu ile stratejinin işlem yapmaya uygunluğunu ayrı kabul kriterleri yapın. Teknik senaryoları sentetik girdilerle doğrulayın; bu sonuçları strateji başarısı olarak raporlamayın. Strateji kabulünde maliyet dahil, görülmemiş veri doğrulaması korunsun.

## 5. Ölçüm Olmadan Parametre Belirleme Yasağı

**Öncelik: Orta — kapsamı fazla geniş kural.**

**Kanıt:** [CLAUDE.md, Mutlak Kurallar](../CLAUDE.md), ölçüm yoksa parametre sabitlenmemesini ister.

**Etki:** Deneysel başlangıç değerleriyle ölçülmüş sonuçlar karışabilir; simülasyon kurmak zorlaşabilir. Kullanıcının zarar toleransı gibi tercihler de yalnızca ölçümle belirlenemez.

**Öneri:** Parametreleri “ölçülmüş”, “deneysel başlangıç değeri” ve “kullanıcı limiti” olarak sınıflandırın. Deneysel değerleri açıkça etiketleyin; canlıya uygun olduklarını varsaymayın.

## 6. Her Teslimde Aynı Uzun Prosedür

**Öncelik: Orta — gereksiz iş yükü riski.**

**Kanıt:** [CLAUDE.md, Faz Durumu ve Kod Konvansiyonları](../CLAUDE.md), faz tesliminde ADR, dosya ağacı, test, kod, Docker, config ve README sırası belirler; testin önce yazılmasını mutlaklaştırır.

**Etki:** Küçük değişiklikler için ilgili olmayan teslim kalemleri üretilmesi riski vardır.

**Öneri:** Teslim gerekliliklerini değişikliğin kapsamına göre seçin. Mimari karar yoksa yeni ADR, container değişmiyorsa Docker işi gerekmemeli. Davranış değişiklikleri anlamlı testlerle doğrulanmalı; dokümantasyon düzeltmesine test zorunluluğu uygulanmamalı.

## 7. Paper/Replay Tutarlılık Şartının Belirsizliği

**Öncelik: Yüksek — kabul kriterinde mantıksal uyumsuzluk.**

**Kanıt:** [Faz 7, Tutarlılık Testi](design/faz7-paper-trading.md), karar dizisinin bit-eşit olmasını isterken gecikme kaynaklı dolum farkına izin verir.

**Etki:** Farklı dolumlar pozisyon durumunu ve sonraki kararları değiştirebilir; geçerli bir koşu yanlışlıkla deterministik değil diye değerlendirilebilir.

**Öneri:** Bit-eşitlik testinde dolum, zaman ve dış olay girdilerini aynı tutun. Farklı dolum modellerinin sonuç karşılaştırmasını ayrı raporlayın. Determinizm şartını kaldırmayın; karşılaştırılan girdileri netleştirin.

## 8. Her Dağıtımdan Önce Bir Gün Paper

**Öncelik: Orta — değişikliğin etkisini dikkate almayan bekleme.**

**Kanıt:** [Faz 10, Geri Dönüş Kuralları](design/faz10-kucuk-sermaye-canli.md), her deploy öncesi en az bir gün paper ister.

**Etki:** Ekran metni düzeltmesi ile emir iletim değişikliği aynı süreye tabi tutulur.

**Öneri:** Doğrulama kapsamını değişikliğin etkisine göre belirleyin. Emir, risk ve muhasebe değişikliklerinde kapsamlı senaryo doğrulaması uygulayın; düşük etkili değişikliklerde ilgili kontrolleri kullanın. Sabit süre tek başına doğruluk kanıtı sayılmamalıdır.

## 9. Gözlem Araçlarının Peşinen Kilitlenmesi

**Öncelik: Düşük — ertelenebilir teknoloji kararı.**

**Kanıt:** [Faz 8 tasarımı](design/faz8-gozlemlenebilirlik.md), Prometheus ve Grafana'yı kilitli seçim olarak belirtir.

**Etki:** Metrik ve alarm ihtiyaçları tamamlanmadan ek servis kurulumu ve işletim yükü doğabilir. Bu araçların gereksiz olduğu kanıtlanmış değildir.

**Öneri:** Önce gerekli metrikleri, alarm senaryolarını ve saklama ihtiyacını belirleyin; bunları karşılayan en basit çözümü seçin. Araç tercihini gereksinimlerden ayrı değerlendirin.

## Korunması Önerilen Kurallar

- Deterministik replay ve gelecekteki verinin kararlara sızmasını önleyen testler.
- Maliyetlerin sonuçlara dahil edilmesi ve varsayımların açıkça raporlanması.
- Borsa tarafı koruma, kalıcı kill switch ve mutabakat.
- Anahtar güvenliği ve canlı işlem için açık kullanıcı onayı.

## Önerilen Öncelik Sırası

1. Eski ve yeni kurallar arasındaki çelişkileri giderin.
2. Teknik kabul ile strateji başarısını ayırın.
3. Paper/replay karşılaştırmasının girdilerini netleştirin.
4. Onay, teslim ve bekleme gerekliliklerini işin etkisine göre daraltın.
5. Gözlem araçlarını ihtiyaçlara göre değerlendirin.

## İnceleme Sınırları ve Yapılmayanlar

Bu çalışma dokümantasyon incelemesidir; testler çalıştırılmadı, servisler denetlenmedi ve güncel borsa API davranışı dış kaynaklarla yeniden doğrulanmadı. Öneriler uygulanmadı. Kullanıcının bulguları kaydetme talebi kapsamında yalnızca bu rapor oluşturuldu; kod, yapılandırma ve mevcut kural belgeleri değiştirilmedi.
