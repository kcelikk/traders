# Frontend veri güncelliği ve doğruluk incelemesi

İnceleme tarihi: 11 Eylül 2026. Saatler UTC'dir.

Bu belge, kullanıcıya ekranda sunulan inceleme çıktısının kaydıdır. Bulgular belirtilen inceleme anına aittir; dosyanın kaydedilmesi sırasında yeniden canlı ölçüm yapılmamıştır. Kullanıcının “çıktıyı kaydet” talebiyle yalnızca bu rapor oluşturulmuştur.

**Konsolun gösterdiği piyasa verisi inceleme sırasında yaklaşık 10–12 saat geriden geliyordu. Ayrıca frontend’de yanlış, sabit veya farklı kaynaklardan karıştırılmış göstergeler var.** İnceleme sırasında dosyalara ve çalışan servislere müdahale edilmedi.

## Canlı API ölçümleri

| Ölçüm — 11 Eylül 2026, UTC | Son gösterilen piyasa olayı | Veri yaşı |
|---|---|---|
| 15:10:57 | 03:39:01 | **11 saat 32 dakika** |
| 15:11:39 | 04:07:38 | **11 saat 4 dakika** |
| 15:13:24 | 05:26:46 | **9 saat 47 dakika** |

API, bu örneklerde `loading=true`, `live=false` ve **“geçmiş kayıt oynatılıyor · ekrandaki değerler canlı değil”** döndürdü.

Buna karşılık kayıt dosyalarının yazılma zamanı günceldi; paper ve testnet canlılık damgaları da birkaç saniye yaşındaydı. **Konsol geçmişi işleyerek ilerliyor; ekranın eski olması, işlem servislerinin de aynı ölçüde geride olduğunu kanıtlamıyor.** Fiyatın ekranda değişmesi de canlı olduğu anlamına gelmiyor: geçmiş kayıt hızlandırılarak oynatılıyor.

Aşağıdaki bulgular kod ve veriyle doğrulandı. Koşula bağlı etkiler ayrıca belirtilmiştir. Dosya/satır referansları inceleme anındaki kaynaklara aittir.

## 1. Yüksek — Geçmiş okuma tamamlanınca daha eski dosyalara dönülebiliyor

Başlangıçta seçilen geçmiş dosyaları `done` listesine ekleniyor; başlangıç penceresinin dışında kalan eski dosyalar eklenmiyor. Sonraki döngü bunları “bekleyen” kabul ediyor.

Mevcut **33 dosya ve 24 dosyalık pencereyle**, seçim mantığı bellekte doğrulandı: geçmiş bölümünden sonra güncel `20260911T1500` dosyası yerine **`20260910T0800`** seçiliyor.

**Etki:** Konsol tekrar geçmişe dönebilir; farklı zamanların olayları aynı durum üzerinde işlenebilir. İnceleme sırasında bu dönüşün gerçekleştiği gözlemlenmedi; seçim hatası doğrulandı.

**Öneri:** Başlangıçta dışarıda bırakılan dosyalar tekrar okunmamalı; okuma imleci ve olay sırası monoton ilerlemeli. Uzun geçmişin yüklenmesi güncel fiyat görünümünü engellememeli.

Kaynak: `fbot/api/server.py:128`.

## 2. Yüksek — Saatlerce eski veride bağlantılar yeşil, K4 “ok”, D3 “EVET” görünebiliyor

Üstteki veri uyarısı gerçek saate göre hesaplanıyor. Bağlantı noktaları ve bazı risk/sinyal göstergeleri ise farklı bir alan olan `stale_flags` kullanıyor.

Canlı yanıtta veri yaklaşık 11 saat eskiyken **`stale_flags={}`** idi. Frontend bunu “bayatlık yok” olarak yorumluyor. Aynı çelişki bellekte de yeniden üretildi.

**Öneri:** Tüm ekranlar ortak tazelik değerlendirmesini kullanmalı; geçmiş yüklenirken sağlıklı/canlı sonucu verilmemeli.

Kaynaklar: `fbot/api/live_view.py:145`, `ui/console-logic.html:182`, `ui/console-logic.html:304`.

## 3. Yüksek — Koşu belirtilmezse görüntülenen ortam kendiliğinden değişiyor

Varsayılan koşu, veritabanı dosyalarının değiştirilme zamanına göre seçiliyor. Paper ve testnet yazmaya devam ettiği için sıralama değişiyor.

Aynı `/api/state` adresi ilk ölçümde **paper**, sonraki ölçümde **testnet** döndürdü; seçim gönderilmedi.

**Etki:** Ortam, performans ve yapılandırma kullanıcı seçimi olmadan değişebilir. Kill switch hedefinin de görüntülenen ortamdan türetilmesi bunu özellikle önemli kılıyor.

**Öneri:** Seçilen ortam ve koşu sabitlenmeli; tüm veri istekleri aynı açık kimlikle yapılmalı.

Kaynaklar: `fbot/api/paper_view.py:27`, `fbot/api/paper_view.py:129`, `ui/console-logic.html:131`.

## 4. Yüksek — Seçilen işlem ortamıyla piyasa verisinin kaynağı aynı değil

Fiyatlar ve piyasa durumları API açılırken belirlenen `rec-72h` kaydından geliyor. Koşu seçimi ise pozisyonları ve yapılandırmayı değiştiriyor; piyasa kaynağını değiştirmiyor.

Açık pozisyon tablosunda brüt sonuç bu ortak kaynağın mark fiyatından, net sonuç seçilen koşunun veritabanından alınıyor. “Maliyet” ikisinin farkı olarak gösteriliyor.

**Etki:** Farklı zaman veya ortam fiyatları nedeniyle brüt/net/maliyet birbirini tutmayabilir. İnceleme anındaki güncel paper/testnet koşularında açık pozisyon yoktu; bu hesap hatasının açık pozisyondaki etkisi canlı olarak ölçülmedi.

**Öneri:** Pozisyon fiyatı, PnL ve maliyet aynı ortamın aynı zamanlı görünümünden gelmeli.

Kaynaklar: `fbot/api/server.py:159`, `ui/console-logic.html:142`.

## 5. Orta — Piyasa durumunun “kaç bardır sürdüğü” yanlış hesaplanıyor

`age_bars`, sınırlı boyuttaki bar listesinin uzunluğundan hesaplanıyor. Liste dolunca uzunluk artmadığından yaş da doğru ilerlemiyor.

Bellekte doğrulanan örnekte, durum değişiminden dört bar sonra beklenen yaş **4**, gösterilen yaş **0** oldu. Canlı API örneğinde de on sembolün tamamında yaş sıfırdı; bunun her biri için gerçek geçiş zamanı ayrıca doğrulanmadı.

**Öneri:** Çekirdekteki gibi bağımsız bar sayacı veya durum başlangıç zamanı kullanılmalı.

Kaynaklar: `fbot/api/live_view.py:98`, `fbot/api/live_view.py:142`.

## 6. Orta — Algoritma ekranında gerçek yapılandırmayı yansıtmayan sabit ifadeler var

Örnekler:

- Ekranda `max_state_age_bars = null`; canlı koşu yapılandırmasında **3**.
- Emir yolu “maker GTX / priceMatch=QUEUE”; çekirdeğin giriş komutu **MARKET**.
- D1 sonucu, “liste boş” ve bazı boru hattı sonuçları sabit yazılmış.
- Pozisyon menü rozeti **`0/5`**, grafik açıklaması **“pozisyon yok”** olarak sabit.

`allowed_cells` güncel paper/testnet koşularında gerçekten boş; bu ifade inceleme anında doğru olsa da yapılandırmadan hesaplanmıyor.

**Öneri:** Açıklamalar etkin koşunun yapılandırması ve gerçek karar kayıtlarından üretilmeli.

Kaynaklar: `ui/console-logic.html:120`, `ui/console-logic.html:258`, `fbot/core/engine.py:265`.

## 7. Yüksek — Bazı risk göstergeleri ölçüm olmadan “ok” yazıyor

Filtreler, emir bütçesi ve 429/418 kontrollerinde güncel doğrulama sonucu yerine sabit veya yapılandırmanın varlığına dayanan “ok” değerleri var. Bazı maruziyet ve spread satırlarının renkleri de gerçek eşik karşılaştırmasına bağlı değil.

**Öneri:** “Yapılandırılmış”, “ölçülmedi”, “son kontrolde geçti” ve “şu an reddediyor” ayrı gösterilmeli. Her sonuç zaman damgası taşımalı.

Kaynak: `ui/console-logic.html:191`.

## 8. Orta — Geçmiş ve performans ekranı açıkken otomatik yenilenmiyor

Ana durum iki saniyede bir sorgulanıyor. İşlem geçmişi ise yalnızca ekrana girildiğinde veya sayfa değiştiğinde yükleniyor.

**Etki:** Yeni kapanan işlemler, ekran açık kaldığı sürece tabloya ve performans grafiğine gelmeyebilir.

**Öneri:** Geçmiş ekranı görünürken kontrollü yenileme yapılmalı ve son güncelleme zamanı gösterilmeli.

Kaynaklar: `ui/console-logic.html:9`, `ui/console-logic.html:44`.

## 9. Orta — API bağlantısı kesilince son “canlı” durumu donabilir

Hata durumunda eski API verisi korunuyor; yalnızca hata metni değişiyor. Veri yaşı son API yanıtındaki sayıya bağlı kaldığından kendiliğinden artmıyor. İsteklerde zaman aşımı ve eski yanıtın yeni yanıtı ezmesini engelleyen kontrol de yok.

**Öneri:** Son başarılı yanıtın yaşı tarayıcıda hesaplanmalı; bağlantı kaybında canlı göstergeleri düşürülmeli ve istek sırası korunmalı. Bu hata yolu çalışan bağlantı kesilerek denenmedi.

Kaynak: `ui/console-logic.html:26`.

## 10. Orta — Maliyet sürüklenmesi göstergesi gerçek maliyet dökümü değil

API hesaplamasında işlem başına sabit **80 USDT**, sabit komisyon, **sıfır funding ve sıfır slippage** kullanılıyor. Sermaye ve alarm eşikleri de sabit.

**Etki:** Bu bölüm gerçek koşunun maliyet ve alarm durumunu yanlış temsil edebilir.

**Öneri:** Koşunun gerçek dolum, komisyon, funding ve sermaye kayıtları kullanılmalı; eksik kalemler sıfır yerine bilinmiyor gösterilmeli.

Kaynak: `fbot/api/server.py:195`.

## 11. Orta — Performans ve araştırma ekranlarında kapsam hataları var

- “Net toplam %” işlem yüzdelerinin toplamı; **hesap sermayesinin getiri yüzdesi değil**. Açıkça adlandırılmalı. Kaynak: `scripts/paper_summary.py:34`.
- Geçmişteki maksimum düşüş frontend’de yalnızca gönderilen son 500 noktadan hesaplanıyor; daha eski büyük düşüş kaybolabilir. Kaynak: `fbot/api/history.py:69`.
- Araştırma tablosu S4 için `cont/rev` ayrımını yapmadan ilk eşleşmeyi alıyor. Dosyada aynı yön ve ufuk için iki ayrı sonuç bulunduğu doğrulandı; biri görünmüyor. Hücre sayısı da senaryo ve keşif/doğrulama kapsamını açık belirtmiyor. Kaynak: `ui/console-logic.html:233`.

## Tarihsel olması beklenen veriler ve derleme kontrolü

**Eski olması tek başına hata olmayan veriler de var.** Gecikme kartındaki **606 ms p99**, geçmiş Faz 0 ölçümünden geliyor ve kartta bu belirtilmiş. Araştırma ve replay sonuçları da tarihsel dosyalardan okunuyor. Bunların canlı olması beklenmez; ancak ölçüm dönemi, üretim tarihi, koşu ve yapılandırma kimliği birlikte gösterilmeli. Kayıt ekranındaki loop lag ise inceleme sırasında konsolun okuduğu eski olaydan geliyordu; güncel recorder sağlığı olarak yorumlanmamalı.

Üretilmiş `ui/index.html` dosyasının mevcut kaynaklardan bellekte oluşturulan çıktıyla **birebir eşleştiği** doğrulandı. Dolayısıyla yerel dosyalarda eski frontend derlemesi sorunu bulunmadı.

## Düzeltme önceliği

Önce geçmiş dosya seçimi ve ortak tazelik hesabı; ardından sabit ortam seçimi ve kaynakların ayrılması; sonra sabit risk/sinyal ifadeleri, geçmiş yenilemesi ve performans hesapları ele alınmalı.

## İnceleme sınırı ve yapılmayanlar

Yerel çalışan API, kayıt dosyalarının zamanları, veritabanları ve frontend/backend kodu incelendi; dosya yazmadan bellek kontrolleri yapıldı. Tarayıcıda görsel inceleme, dış erişim/CDN önbelleği kontrolü ve tam test paketi çalıştırılmadı. **Hiçbir düzeltme veya servis yeniden başlatma yapılmadı.**

Bu raporun kaydedilmesi, bulgulardaki önerilerin uygulanması anlamına gelmez. Kullanıcının sonraki açık talebiyle yalnızca bu dokümantasyon dosyası oluşturuldu.
