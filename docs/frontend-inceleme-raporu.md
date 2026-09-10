# Frontend İnceleme Raporu

Tarih: 2026-09-10 · İncelenen son HEAD: `95bcc79`

## Kapsam ve yöntem

`ui/index.html`, destek şablonları, `fbot/api/`, paper metrikleri, ortam yapılandırmaları, Docker volume eşlemeleri ve ilgili API testleri salt okunur incelendi. Bu rapor kullanıcının açık dosyaya kaydetme talebiyle oluşturuldu; uygulama dosyaları değiştirilmedi. Çalışma sırasında depo başka geliştirmelerle ilerlediğinden satır numaraları inceleme anını gösterir.

Tarayıcı otomasyonu/görsel ekran doğrulaması yapılmadı; mevcut araçlarda tarayıcı aracı bulunmadı. Testler çalıştırılmadı, servis başlatılmadı, anahtar dosyaları okunmadı, kill/reset veya anahtar yazma uçları çağrılmadı. Aşağıdaki doğrulama senaryoları öneridir; çalıştırılmış test sonucu değildir. Koddan kesinleşen davranışlar ile görsel doğrulama gerektiren riskler ayrılmıştır. Kârlılık gösterilmedi.

## Genel sonuç

Konsolda gerçek veri bağlantıları mevcut; ancak Config, Risk, Algoritma ve doğrulama göstergelerinde sabit taslak değerler kalmış. En önemli sorun, seçilen ortam ile kontrolün hedefi ve gösterilen verinin kaynağının aynı olmaması. Bu durum konsolun operasyonel kararlar için güvenilirliğini azaltıyor.

## F01 — Ortam seçimi kill switch hedefini değiştirmiyor

**Önem: Yüksek · Durum: Kodla doğrulandı.**

**Kaynak:** `ui/index.html:711–712`; `fbot/api/server.py` — `Api.__init__`, `do_POST`; `docker-compose.yml:75`; `fbot/paper/main.py:49`.

UI testnet koşusunu seçse de kill/reset istekleri ortam veya koşu kimliği taşımıyor. API sabit `data/state/kill_switch.json` dosyasına işlem yapıyor. Testnet container'ı ise host üzerindeki `data/state/testnet` dizinini kendi `/app/data/state` yoluna bağlıyor.

**Etki:** Testnet ekranındaki kill işlemi testnet kill dosyasını hedeflemiyor; kullanıcı seçili ortamı durdurduğunu sanabilir.

**Öneri:** Ortam/koşu kimliğini istek sözleşmesine ekleyin; sunucuda izinli ortam-dosya eşlemesi kullanın. Onay ekranında hedefi açıkça gösterin. **Doğrulama:** Her ortam için ayrı geçici kill dosyasıyla yalnızca seçilen hedefin değiştiğini test edin.

## F02 — Config ekranı etkin koşunun ayarlarını göstermiyor

**Önem: Yüksek · Durum: Kodla doğrulandı.**

**Kaynak:** `fbot/api/server.py:55–70`; `config/paper.toml`; `ui/index.html:517,646–647`.

`assemble_config` yalnızca recorder/research TOML dosyalarını okuyor; pozisyon ve risk verileri sabit `POSITION_DEFAULTS`/`RISK_DEFAULTS`. Örneğin paper beta tavanı 750 iken API `None`; paper kâr kilidi ve zaman aşımı değerleri varken ekranda kapalı görünebiliyor. Config hash'i de HTML içinde sabit. Testnet için kilitli emir yolu metni WS/Ed25519 olarak kalmış.

**Etki:** Kullanıcı etkin korumaları ve emir yolunu yanlış değerlendirir.

**Öneri:** Koşuyla birlikte kaydedilmiş etkin yapılandırmayı, ortamı ve hash'i gösterin; güncel dosya ile koşu başlatılırken kullanılan ayarı ayırın. **Doğrulama:** Farklı parametreli paper/testnet koşularında ekranın doğru kaynağa geçtiğini kontrol edin.

## F03 — Risk ekranında ölçülmeyen kontroller sağlıklı gösteriliyor

**Önem: Yüksek · Durum: Kodla doğrulandı.**

**Kaynak:** `ui/index.html:654`.

K6 sürekli `0/5`, K8 `0 USDT`, K9 `kapalı`, K2 `paper başlamadı`; K7/K12/K18 sabit `ok`. Slippage yaklaşık sıfır olarak sabit gösteriliyor. Bunlar güncel risk motoru sonucundan türetilmiyor.

**Etki:** Açık pozisyon veya risk sorunu varken yeşil durum gösterilebilir.

**Öneri:** Risk girdisi, sonucu ve değerlendirme zamanını API'den taşıyın; veri yoksa “bilinmiyor” gösterin. **Doğrulama:** Ret, bayatlık ve eksik veri senaryolarında ilgili kontrolün doğru duruma geçtiğini sınayın.

## F04 — Seçilen koşu ile piyasa görünümü farklı kaynaklardan geliyor

**Önem: Yüksek · Durum: Kodla doğrulandı.**

**Kaynak:** `fbot/api/server.py` — `Api.__init__`, `state`, `_paper`; `ui/index.html:621–625,713`.

`?run=` SQLite pozisyon/karar kaynağını değiştiriyor; grafik, mark fiyatı, piyasa durumu ve ısınma görünümü sabit recorder/research kaynağında kalıyor. Pozisyon brüt getirisi bu ayrı görünümün mark fiyatıyla hesaplanıyor.

**Etki:** Testnet veya farklı parametreli demo koşusunun pozisyonları başka akışın fiyatları ve ısınmasıyla birlikte gösterilir.

**Öneri:** Her panelin ortam, koşu, veri zamanı ve yapılandırma kaynağını belirtin; işlem ekranlarını seçilen koşuya bağlayın. **Doğrulama:** Farklı sembol ve W değerleri olan iki koşuyu seçerek tüm panelleri karşılaştırın.

## F05 — Koşu varlığı çalışma kanıtı sayılıyor; yanlış koşuya sessiz dönüş var

**Önem: Yüksek · Durum: Kodla doğrulandı.**

**Kaynak:** `fbot/api/server.py` — `_paper` (`paper_running`); `fbot/api/paper_view.py:56–62`; `ui/index.html:607,655`.

`paper_running` yalnızca veritabanı koşusu bulunmasına bağlı. Durum menüsündeki “canlı” etiketi veri tazeliğini kontrol etmiyor. İstenen run bulunamazsa `or runs` ile en yeni başka koşuya dönülüyor.

**Etki:** Durdurulmuş süreç çalışıyor sanılabilir; hatalı URL başka ortama ait sonuçları gösterebilir.

**Öneri:** Heartbeat ve son olay zamanıyla çalışan/bayat/durdu durumlarını ayırın; bulunamayan koşuda açık hata verin. **Doğrulama:** Eski veritabanı ve geçersiz run seçimiyle davranışı sınayın.

## F06 — Açık pozisyonlar son 50 kayıt sınırında kaybolabilir

**Önem: Yüksek · Durum: Kodla doğrulandı; gerçekleşmesi veri dağılımına bağlı.**

**Kaynak:** `fbot/api/paper_view.py:65–79`; `ui/index.html:607,633,661`.

Pozisyon sorgusu açık/kapalı ayrımı yapmadan en yeni 50 kaydı getiriyor. Açık pozisyon sayacı tüm veritabanından hesaplanıyor. Menü rozeti ayrıca sabit `0/5`.

**Etki:** Uzun süre açık kalan pozisyon daha yeni 50 kayıt varsa tabloda görünmez; sayaç, tablo ve maruziyet farklılaşır.

**Öneri:** Tüm açık pozisyonları ayrı sorgulayın; kapalı geçmişe sayfalama ekleyin ve rozeti gerçek sayaca bağlayın. **Doğrulama:** Bir eski açık ve 50 yeni kapalı pozisyon içeren veriyle kontrol edin.

## F07 — Maruziyet, maliyet ve ROE değerleri gerçek hesap verisinden gelmiyor

**Önem: Yüksek · Durum: Kodla doğrulandı.**

**Kaynak:** `ui/index.html:625–633,661–662,713`.

Maruziyet açık kayıt sayısı × 80; maliyet sabit `%0.10`; kaldıraç sembole göre 10x/5x. Teminat göstergesi `grossNow / 10` sonucunu yüzde olarak sunuyor; hesap bakiyesiyle oranlanmıyor. BTC-beta maruziyeti sıfır sabit. Kapalı pozisyonun brüt sütunu da güncel mark fiyatından hesaplanıyor.

**Etki:** Kısmi dolum, azaltma, değişen kaldıraç ve kapalı pozisyonlarda yanlış finansal gösterimler oluşur.

**Öneri:** Gerçek miktar, ilgili fiyat, gerçekleşen maliyet ve hesap teminatını kullanın; veri yoksa sayı üretmeyin. Kapalı işlemlerde çıkış fiyatını kullanın. **Doğrulama:** Kısmi dolumlu ve farklı kaldıraçlı örneklerin elle hesaplanmış sonuçlarıyla karşılaştırın.

## F08 — Toplam yüzde getirisi ve drawdown gösterimi yanıltıcı

**Önem: Orta · Durum: Kodla doğrulandı.**

**Kaynak:** `scripts/paper_summary.py:13–33`; `ui/index.html:713`.

`net_toplam_pct`, işlem bazlı yüzdelerin toplamı; UI bunu “NET (ORTAM) %” olarak sunuyor. Hesap özkaynağı getirisi değil. Drawdown döngüsüne giren kapanmış pozisyon sorgusunda `ORDER BY closed_ns` yok.

**Etki:** Hesap performansı yanlış yorumlanabilir; kapanış sırası farklı olduğunda drawdown yanlış hesaplanabilir.

**Öneri:** İşlem yüzdesi toplamını açık etiketleyin; hesap getirisi için USDT PnL ve sermaye tabanı kullanın. Drawdown'u zaman sıralı özkaynak serisinden üretin. **Doğrulama:** Açılış ve kapanış sıraları farklı işlemlerle beklenen drawdown'u karşılaştırın.

## F09 — SHA ve replay doğrulama göstergeleri sabit başarı yazıyor

**Önem: Yüksek · Durum: Kodla doğrulandı.**

**Kaynak:** `ui/index.html:491,671,721`; `fbot/api/server.py` — `recorder_files`.

Her dosyada koşulsuz `SHA ✓` var; API dosya adı ve boyutu döndürüyor, checksum doğrulama sonucu yok. Replay process hash'leri ve başarı satırları sabit; hız da 65k olarak sabit gösteriliyor.

**Etki:** Yeni veya bozuk dosya doğrulanmış sanılabilir; tarihsel test güncel kodun sonucu gibi algılanabilir.

**Öneri:** Doğrulama raporunu dosya/hash/commit/zaman ile eşleyin. Açık veya kontrol edilmemiş dosyada “doğrulanmadı” gösterin. **Doğrulama:** Kontrol edilmemiş ve checksum'u bozuk fixture'larda yeşil onay oluşmadığını sınayın.

## F10 — Algoritma ve faz ekranlarında eski sabit açıklamalar var

**Önem: Orta · Durum: Kodla doğrulandı.**

**Kaynak:** `ui/index.html:52,408,666,691,698`.

Üst başlık Faz 4 olarak sabit; durum satırları `allowed_cells boş`, intent sonucu `None · intent üretilmedi`, SL/TP açıklaması null olarak sabit. Demo/testnet koşusunun gerçek kararları bu metinleri değiştirmiyor. Rapor hash'i bazı panellerde sabit.

**Etki:** Karar tablosunda emir görülürken algoritma ekranı hiç intent üretilmediğini söyleyebilir.

**Öneri:** Seçili koşunun karar ve config verilerini gösterin; açıklama amaçlı şemayı anlık durumdan ayırın. **Doğrulama:** Intent üreten demo ile boş allowed_cells kullanan koşuyu karşılaştırın.

## F11 — Okuma koruması frontend ile uyumlu değil

**Önem: Orta · Durum: Kodla doğrulandı; protect_reads etkinliğine bağlı.**

**Kaynak:** `ui/index.html:563,809`; `fbot/api/auth.py` — `check`; `fbot/api/server.py` — `--protect-reads`.

GET `/api/state` ve `/api/keys` çağrıları saklanan uygulama token'ını göndermiyor. Okuma koruması açılırsa geçerli token localStorage'da olsa da kullanılmıyor. State polling HTTP durumunu kontrol etmeden JSON'u veri sayıp `api.universe[0]` okuyor.

**Etki:** Okuma korumasında ekran yüklenmeyebilir; kullanıcı anlamlı giriş mesajı yerine teknik hata görebilir. Ayrı Basic Auth parolasının uygulama token'ına eşit olduğu varsayılamaz.

**Öneri:** Ortak API istemcisiyle GET/POST kimlik doğrulaması, HTTP durum kontrolü ve tekrar giriş akışı sağlayın. **Doğrulama:** Korumalı okumada geçerli/eksik/yanlış token senaryolarını sınayın.

## F12 — Kill/reset isteklerinde hata ve işlem durumu eksik

**Önem: Orta · Durum: Kodla doğrulandı.**

**Kaynak:** `ui/index.html:565–569,711–712`.

`post()` yalnızca 401'i özel işliyor; diğer hata yanıtları sonrası polling yapıyor. Ağ hatası için catch yok. Kill modalı istek tamamlanmadan kapanıyor; bekleme durumunda düğme kilidi yok. Reset doğrudan gönderiliyor.

**Etki:** Kullanıcı işlemin gerçekleşip gerçekleşmediğini anlayamayabilir; tekrar tıklamalar oluşabilir.

**Öneri:** İstek süresince düğmeyi kilitleyin, tüm hata durumlarını gösterin ve başarıyı sunucu yanıtıyla doğrulayın. Hedef ortamı reset için de gösterin. **Doğrulama:** 401/400/500, ağ kesintisi ve gecikmeli yanıt senaryolarını sınayın.

## F13 — Mobil düzen ve modal erişilebilirliği eksikleri

**Önem: Orta · Durum: Statik eksik; görsel etki doğrulanmadı.**

**Kaynak:** `ui/index.html:71,88,537–543`; anahtar modalı ve stil bloğu.

Ana düzen sabit 200px yan menü ve çok sütunlu içerik kullanıyor; responsive medya kuralları görülmedi. Kök yatay taşmayı gizliyor. Kill modalında dialog/aria-modal semantiği, Escape ve odak yönetimi görünmüyor; anahtar panelinde de klavye odak akışı için doğrulama gerekli.

**Etki:** Dar ekranlarda içerik sıkışması/kırpılması ve klavye kullanıcılarının modal dışına çıkması riski.

**Öneri:** Mobilde daralan menü ve tek sütun düzen; modal odak sınırı, Escape, etiketler ve açan düğmeye odak dönüşü ekleyin. **Doğrulama:** 360/768/1440px, %200 zoom ve yalnızca klavyeyle gezinme. Bu kontroller bu incelemede yapılmadı.

## Eksik ekran/veri kapsamı

- Etkin koşunun tam risk, karar, simülasyon ve hesap yapılandırması ile gerçek config hash'i.
- Süreç heartbeat'i, son başarılı güncelleme ve açık veri-bayatlığı uyarısı.
- Ortama özel mutabakat, emir bütçesi, koruma ACK ve kill durumu.
- Açık emirler/kısmi dolumlar için ayrıntı; kapalı pozisyon ve karar geçmişinde sayfalama.
- Finansal kartlarda veri kaynağı, hesaplama tanımı ve zaman aralığı.
- FROZEN/EMERGENCY sayılarının mevcut FSM özetinde dinamik olarak gösterilmesi (`ui/index.html:644` listesi bu durumları içermiyor).

Config ekranının salt okunur olması tek başına hata değildir; düzenleme talebi veya onaylı tasarım gereksinimi olmadan ayar değiştirme yeteneği önerilmemiştir.

## Önerilen düzeltme sırası

1. Ortama özel kill hedefi ve koşu seçiminde yanlış kaynağa dönüşü engelleme.
2. Etkin config/risk verisini bağlama; sahte yeşil doğrulamaları kaldırma.
3. Açık pozisyonların eksiksiz gösterimi ve finansal hesaplamalar.
4. Token, HTTP hata ve tazelik durumları.
5. Dinamik algoritma/faz metinleri, mobil düzen ve erişilebilirlik.

## Teslim sınırı

13 bulgu kaydedildi. Uygulama düzeltmesi, canlı işlem, anahtar değişikliği veya sistem müdahalesi yapılmadı. Bulguların giderilmesi sonrası aynı senaryolarla yeniden doğrulama gerekir.
