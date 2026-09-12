# Endpoint uyumu ve frontend statik veri incelemesi

Tarih: 2026-09-12. HEAD: `14782f7dfcc3`; değerlendirme mevcut çalışma ağacı üzerindedir. Başlangıçta `fbot/core/risk.py` değişik, `fbot/core/lease.py`, `fbot/strategy/`, `tests/test_lease.py`, `tests/test_strategy_platform.py` izlenmeyen dosyalardı; bu çalışmada bunlara dokunulmadı.

## Sonuç

Backend **7**, frontend **6** API işlemi içeriyor. Frontend'in kullandığı altı yöntem/yol çiftinin tamamının backend karşılığı var. Backend'deki `GET /api/health` frontend tarafından kullanılmıyor; bu tek başına eksiklik değildir. **Adres eşleşmesi tamam; veri anlamı, tazelik, hata yönetimi ve ekran doğruluğu bakımından tam uyum yok.**

Frontend'de gerçek veriye bağlanmamış rakam ve durumlar **var**. Özellikle `31% → 18%`, `−0.04% → −0.01%`, sabit git/config kimlikleri, `SHA ✓`, `%38` disk çubuğu, `0/5` rozeti ve bazı “ok/aktif/mutabakat tamam” ifadeleri gerçek ölçüm veya etkin koşu durumundan üretilmiyor.

20 bulgu kayıt altına alındı: **7 yüksek, 13 orta**. Yüksek bulgular EP01–EP05, EP09 ve EP10. Bunlar işlem motorunun zarar verdiğini kanıtlamaz; operatöre sunulan bilginin veya işlem hedefinin doğruluğuyla ilgilidir. Kârlılık gösterilmedi; bu inceleme performans/kârlılık ölçümü değildir.

## Doğrulama yöntemi ve kanıt düzeyi

1. Route tanımları, tüm uygulama `fetch` çağrıları, üretilen HTML, build şablonu ve yanıt üreticileri okundu. Vendor kodu uygulama endpoint'i olarak sayılmadı.
2. Backend yolları AST ile çıkarıldı; frontend çağrıları yöntem, sorgu, gövde, token ve yanıt alanları bakımından karşılaştırıldı: **eksik backend karşılığı 0**.
3. Yedi gerçek handler metodu bellekte çağrıldı; veri kaynakları ve yazma yan etkileri mock edildi. Yedi başarı dalı, run/limit/offset aktarımı, 401 ve eksik env 400 doğrulandı. Sunucu açılmadı, gerçek POST yapılmadı.
4. Aynı bellek denetiminde `/api/state-does-not-exist` 200 state dalına gitti; bozuk JSON `JSONDecodeError`, `[]` gövdesi `AttributeError` üretti.
5. `python3 -B -m scripts.build_ui --check`: **güncel**. `tests/test_ui_build.py` içindeki altı kontrol dosya yazmadan doğrudan çağrıldı: **6/6 geçti**. Bunlar şablon/parantez/bağlama/build kontrolleri; tarayıcı testleri değil.
6. Çalışan serviste yalnız `GET /api/state` okundu. Yanıt zamanı **11:33:43.064 UTC**; seçili `paper` koşusu, `freshness=live`, veri yaşı `0.2 s`, `recorder.frames` yok, `decision.max_state_age_bars=3`. Bir anlık gözlem süreklilik garantisi değildir.

“Doğrulandı” aşağıda kod/yanıt/yönlendirme düzeyinde kanıtlanan durumu belirtir. Koşula bağlı etkiler ayrıca yazılmıştır; tarayıcıda veya gerçek emir/anahtar değişiminde yeniden üretildiği iddia edilmez.

## Bulgular

### EP01 — Yüksek — Performans kartları ölçümden gelmiyor

**Kanıt:** [index.html:244](../ui/index.html:244) ve [245](../ui/index.html:245) içinde `31% → 18%` ve `−0.04% → −0.01%` literal HTML. Kaynak [tasarım:227](../ui/design/fbot%20Console.dc.html:227); build bu metinleri değiştirmiyor. **Doğrulandı:** API/replay sonucu değişse veya hiç olmasa da rakamlar aynı kalır. **Etki:** örnek yüzdeler ölçülmüş strateji sonucu gibi görünür. **Öneri:** rapor verisine bağla; run, ölçüm zamanı ve örneklem göster; veri yoksa ölçülmedi yaz. **Kapanış:** iki farklı replay yanıtı ve eksik rapor senaryosunda kartların doğru değişmesi.

### EP02 — Yüksek — SHA doğrulaması yapılmadan başarılı rozeti var

**Kanıt:** [index:502](../ui/index.html:502) her satırda sabit `SHA ✓` basıyor; [server:70](../fbot/api/server.py:70) yalnız ad/boyut üretiyor. [logic:295](../ui/console-logic.html:295) dosya listesine koşu özetlerini de ekliyor. **Doğrulandı:** API'de hash doğrulama alanı yok; koşu satırlarında bile rozet var. **Etki:** bozuk veya doğrulanmamış kayıt sağlam sanılabilir. **Öneri:** dosya bazlı doğrulama sonucu/zamanı olmadan başarı göstermeme; koşu özetlerini dosya doğrulamasından ayırma. **Kapanış:** doğrulanmamış ve bozuk dosyada yeşil SHA görünmemesi.

### EP03 — Yüksek — Risk tablosu güncel risk motoru durumunu göstermiyor

**Kanıt:** [logic:240](../ui/console-logic.html:240), [245](../ui/console-logic.html:245): K6/K8 için config varlığı, K13 için sabit `ok`, K17 için config varlığı başarı rengi üretir; K7 metni `ÇAKIŞMA` olsa bile rengi `ok`. K5 offline `latency.skew.p99`, K3/K4 recorder görünümü, K18 recorder sayacını kullanır. [server:335](../fbot/api/server.py:335) recorder snapshot'ını, [342](../fbot/api/server.py:342) seçili koşuyu ayrı toplar. **Doğrulandı:** kaynaklar farklı ve bazı renkler eşik karşılaştırmasına bağlı değil. **Koşula bağlı etki:** testnet dururken recorder canlıysa veya limit aşılmışken henüz ret kaydı yoksa olumlu rozet yanıltabilir. `kHit` ayrıca eski retleri güncel durum gibi gösterebilir. **Öneri:** seçili trader'ın zaman damgalı risk girdisi/sonucu; bilinmiyor ve geçmiş ret ayrımı. **Kapanış:** limit aşımı, boş veri ve recorder canlı/trader bayat senaryoları doğru uyarı üretmeli.

### EP04 — Yüksek — Backend maliyet görünümü sabit varsayımlar içeriyor

**Kanıt:** [server:298](../fbot/api/server.py:298): sermaye `1000`, notional `80`, komisyon `80 × 0.001`, funding/slippage `0`; sorguda entry/qty alınsa da kullanılmıyor. [logic:271](../ui/console-logic.html:271) bunu alarm veya “eşik içinde” diye sunuyor. **Doğrulandı:** bunlar gerçek işlem maliyetleri değil. Örneğin 160 notional kaydı da 80 üzerinden komisyonlanır. Çalışan örnekte `trades=0`, dolayısıyla o anda yanlış maliyetli işlem gösterildiği ileri sürülmüyor. **Öneri:** kaydedilmiş dolum/maliyet ve koşu config'i; eksikse bilinmiyor veya açık model etiketi. **Kapanış:** değişken notional/komisyon/funding/slippage içeren kayıtlar elle hesaplanan sonuçla eşleşmeli.

### EP05 — Yüksek — “Servis yeni anahtarı aldı” kanıtı yetersiz

**Kanıt:** [keys-panel:97](../ui/keys-panel.html:97): `armed===true && age_s<60` başarı sayılır. [paper_view:87](../fbot/api/paper_view.py:87) uygulanan credential sürümü veya uygulama zamanı dönmüyor. **Doğrulandı:** eski ama taze silahlı heartbeat ile yeni anahtarın alınması ayırt edilemez; devre dışı bırakma da aynı kontrolü kullanır. **Koşula bağlı etki:** açık pozisyon nedeniyle ertelenmiş anahtar değişimi tamamlandı veya disarm isteği yanlış başarılı/reddedilmiş sanılabilir. **Öneri:** POST'ta credential sürümü, heartbeat'te applied_version/applied_at ve hedef armed durumu; bekliyor/uygulandı/reddedildi ayrımı. **Kapanış:** eski heartbeat yeni sürümü onaylamamalı; arm/disarm ve ertelenmiş değişim ayrı doğrulanmalı.

### EP06 — Orta — Gösterilen git/config kimlikleri sabit

**Kanıt:** [index:75](../ui/index.html:75) `git 8271224 · cfg 75a167d`, [index:528](../ui/index.html:528) `config hash 75a167d`. Buna karşılık backend `recorder.git_sha`, `paper.config_hash`, `config.run.git_sha` taşıyor. **Doğrulandı:** üstteki kimlikler API'ye bağlı değil; inceleme HEAD'i de farklı. **Etki:** operatör yanlış sürüm/konfigürasyona baktığını sanabilir. **Öneri:** recorder ve seçili trader kimliklerini ayrı adlandırıp gerçek kayda bağla. **Kapanış:** run değişiminde doğru kimlik, eksik kayıtta `—`.

### EP07 — Orta — D1/D2/D3 ve sinyal açıklamaları kısmen sabit

**Kanıt:** [logic:282](../ui/console-logic.html:282), [312](../ui/console-logic.html:312), [313](../ui/console-logic.html:313), [315](../ui/console-logic.html:315), [527](../ui/console-logic.html:527): `allowed_cells boş`, D1 `HAYIR`, `max_state_age_bars=null`, `D1 başarısız`, eski kimlik şablonu/80 USDT/null SL-TP. **Doğrulandı:** çalışan state'te yaş sınırı **3**, açıklamada **null**. `allowed_cells` örnekte gerçekten boş; listenin boşluğu o an yanlış değil, sabitlenmesi sorun. **Öneri:** etkin `config.decision` ve son verdict; açıklayıcı örnek varsa örnek etiketi. **Kapanış:** boş/dolu liste ve değişen yaş/SL/TP ile açıklama/sonuç tutarlılığı.

### EP08 — Orta — Frontend'in beklediği `recorder.frames` üretilmiyor

**Kanıt:** [logic:293](../ui/console-logic.html:293) bu alanı okur; [live_view:153](../fbot/api/live_view.py:153) snapshot'a koymaz. Çalışan state alan listesinde de yok. **Etki:** akış sayaçları sürekli `—`; mevcut kod kategori toplamını akış satırlarına dağıtmayı hedefliyor. **Öneri:** kategori/akış sayaç sözleşmesini açıkça tanımla ve üretici-tüketiciyi eşleştir. **Kapanış:** gerçek kaydın bilinen kategori/akış adetleri doğru etikette görünmeli.

### EP09 — Yüksek — Eksik koşu seçiminde endpoint'ler farklı davranıyor

**Kanıt:** [paper_view:134](../fbot/api/paper_view.py:134) `want or runs` ile başka koşuya döner, [history:39](../fbot/api/history.py:39) aynı istek için boş yanıt verir. [_drift:292](../fbot/api/server.py:292) de fallback yapar. [logic:183](../ui/console-logic.html:183) kill ortamını dönen koşudan seçer. **Doğrulandı:** aynı `run` için tutarsız seçim sözleşmesi; UI `run_missing` uyarısı veriyor ama fallback'i ve kill erişimini engellemiyor. **Koşula bağlı etki:** yanlış koşu/maliyet görüntüleme ve başka ortama yönelen kill/reset kontrolü. **Öneri:** açıkça seçilmiş eksik run için ortak boş/404 davranışı ve yazma kontrollerinin kapanması. **Kapanış:** olmayan run ile state/history aynı sonucu vermeli; fallback ortamında kill/reset kullanılamamalı.

### EP10 — Yüksek — Kill ve mutabakat açıklamaları sağlık modeliyle çelişiyor

**Kanıt:** [index:191](../ui/index.html:191), [logic:574](../ui/console-logic.html:574), [build_ui:79](../scripts/build_ui.py:79) kill/bayatlıkta `FROZEN` der. [logic:451](../ui/console-logic.html:451) mutabakat yokken “çıkışlar serbest” der. Oysa [health:50](../fbot/core/health.py:50) mutabakatsızlığı `HALTED`, bayatlığı `PROTECTION_ONLY` yapar; [engine:300](../fbot/core/engine.py:300) HALTED'da kural emri üretmez. **Doğrulandı:** uygulama çıkış davranışının açıklaması güncel kodla uyumsuz. Risk veto muafiyeti ile sağlık modelinin emir üretimini durdurması farklı katmanlardır. **Öneri:** heartbeat `exit_mode` gösterimi ve ADR 0021 ile açıklamaların güncellenmesi. **Kapanış:** FULL/PROTECTION_ONLY/HALTED ve kill senaryolarında doğru açıklama.

### EP11 — Orta — Anahtar paneli hata/uyarı sözleşmesini eksik tüketiyor

**Kanıt:** [keys-panel:91](../ui/keys-panel.html:91) GET'te `r.ok` kontrol etmez; 401 JSON'u `status` içermeyince sessiz kalabilir. [keys:114](../fbot/api/keys.py:114) sahiplik hatasını `warning` olarak döndürür; [keys-panel:123](../ui/keys-panel.html:123) yalnız `error/note` kontrol eder. **Etki:** eski durum panelde kalabilir; anahtarın servisçe okunamama uyarısı kaybolur. **Öneri:** ortak istemci/hata politikası, warning gösterimi ve başarısız okumada eski durumun işaretlenmesi. **Kapanış:** 401, 500, JSON olmayan yanıt ve 200+warning senaryoları görünür hata/uyarı üretmeli.

### EP12 — Orta — Poll/geçmiş isteklerinde tazelik ve sıralama koruması yok

**Kanıt:** [logic:10](../ui/console-logic.html:10), [17](../ui/console-logic.html:17), [38](../ui/console-logic.html:38): state istekleri çakışabilir; istek numarası/iptal/timeout yok. Hata eski `api`yi korur; [logic:166](../ui/console-logic.html:166) eski `freshness.live` değerini kullanır. Geçmiş yalnız ekran/sayfa değişiminde yüklenir; periyodik yenileme yok. **Doğrulandı:** korumalar yok. **Koşula bağlı etki:** geç yanıt yenisini ezebilir; state hata başlığı görünse bile eski canlı rozeti kalabilir; açık geçmiş ekranı yeni işlemleri kaçırır. **Öneri:** en güncel isteği kabul etme, bağlantı/tazelik zaman damgası ve geçmiş yenilemesi. **Kapanış:** ters yanıt sırası, kesinti ve yeni kapanış senaryoları.

### EP13 — Orta — Geçmişte MAKS DD tüm koşuyu kapsamıyor

**Kanıt:** [history:69](../fbot/api/history.py:69) equity'yi son 500 ile sınırlar; [logic:321](../ui/console-logic.html:321) ve [329](../ui/console-logic.html:329) yalnız bu parçadan “MAKS DD” hesaplar. Grup toplamları bütün işlemlerden gelir. **Doğrulandı:** özetlerin kapsamı farklı. **Koşula bağlı etki:** 500'den önceki zirve/düşüş kaybolursa maksimum düşüş eksik gösterilir. **Öneri:** tüm seriden backend özeti veya açık pencere etiketi; grafik noktası sınırı özetin doğruluğunu değiştirmemeli. **Kapanış:** ilk bölümde büyük düşüş içeren >500 işlemle referans hesabı eşleştirme.

### EP14 — Orta — Yol ve hata yanıtları tutarlı değil

**Kanıt:** [server:398](../fbot/api/server.py:398) GET'te prefix eşleşmesi; [423](../fbot/api/server.py:423) bilinmeyen GET'i statik sunucuya aktarır; POST'ta tam yol/JSON 404. Bellekte `/api/state-does-not-exist` **200** döndü. **Etki:** yazım hataları gizlenir, API hata gövdesi HTML/JSON arasında değişir. **Öneri:** parse edilmiş pathname üzerinde tam route eşleşmesi ve ortak JSON 404/405 politikası. **Kapanış:** fazladan son ek, slash, query, bilinmeyen yol ve yöntem matrisi.

### EP15 — Orta — Hatalı POST gövdesi kontrollü hataya çevrilmiyor

**Kanıt:** [server:428](../fbot/api/server.py:428) JSON parse ve Content-Length dönüşümü korunmuyor; devamında gövde nesne kabul ediliyor. Bellekte `{` → `JSONDecodeError`, `[]` → `AttributeError`. **Etki:** frontend anlamlı 400 yerine bağlantı/parse hatası görebilir. **Öneri:** JSON nesnesi, içerik boyutu/türü ve alan tiplerinin doğrulanması; standart 400/413 yanıtı. **Kapanış:** bozuk JSON, dizi/null, hatalı uzunluk ve sınır aşımı senaryoları kontrollü yanıt vermeli.

### EP16 — Orta — Topoloji/private ve yeni telemetri gösterimi eksik

**Kanıt:** [logic:359](../ui/console-logic.html:359) recorder canlılığını seq varlığı + loading olmamasından çıkarır; bayatlık yeterince hesaba katılmaz. [383](../ui/console-logic.html:383) `reconciled` undefined iken “mutabakat tamam”; [124](../ui/console-logic.html:124) bazı kutuları sabit live yapar; [567](../ui/console-logic.html:567) noktanın heartbeat'ten geldiğini söyler. [index:68](../ui/index.html:68) private “anahtar yok”, [logic:531](../ui/console-logic.html:531) private noktası sabit kapalıdır. [testnet:413](../fbot/testnet/main.py:413) breaker/exit_mode/telemetry üretir; UI bunları işlemez. [logic:513](../ui/console-logic.html:513) bütün süreçleri aynı beş akışla anlatır; [config:22](../fbot/config.py:22) roller farklıdır. **Etki:** bilinmeyen/canlı olmayan bileşen olumlu görünebilir; yeni güvenlik ölçümleri görünmez. **Öneri:** rol bazlı zaman damgalı sağlık ve unknown durumu, telemetri alanlarının ekrana bağlanması. **Kapanış:** heartbeat yok/bayat/false ve farklı stream profilleriyle doğru gösterim.

### EP17 — Orta — Kaldıraç/ROE ve bazı başlıklar sabit varsayıma bağlı

**Kanıt:** [logic:201](../ui/console-logic.html:201), [212](../ui/console-logic.html:212), [220](../ui/console-logic.html:220), [551](../ui/console-logic.html:551) BTC/ETH 10x, diğerleri 5x kullanır. Config'te sembol bazlı `risk.leverage/default_leverage` var; borsa doğrulanmış kaldıraç pozisyon sözleşmesinde yok. [index:198](../ui/index.html:198) başlıkta 80 USDT/tick 1000 sabittir. **Doğrulandı:** hesap ve başlıklar etkin kaynaktan türetilmiyor; mevcut config varsayımla örtüşebilir. **Etki:** farklı koşu/hesapta ROE ve açıklamalar yanlış olur. **Öneri:** configured/verified leverage ayrımı, doğrulanmamış ROE etiketi ve dinamik başlık. **Kapanış:** farklı kaldıraç/notional/tick ve eksik kaldıraç senaryoları.

### EP18 — Orta — Disk, replay, rozet ve ortam adlarında kalan statik bilgi

**Kanıt:** [index:504](../ui/index.html:504) `~220 MB/saat`, [505](../ui/index.html:505) `%38`; [509](../ui/index.html:509) `%96.9–99.7`, `pu kopuşu 0`, “her snapshot'ta başarılı”. [orderbook raporu](orderbook-replay-hour1.md:7) geçmiş ölçüm içerir, sıfır olmayan gap/resync sayıları vardır; ekran bu raporu okumaz. [logic:171](../ui/console-logic.html:171) `0/5`; [83](../ui/console-logic.html:83) grafikte sabit “pozisyon yok”; [index:72](../ui/index.html:72) LIVE yazan düğme [logic:533](../ui/console-logic.html:533) ile testnet seçer. [logic:233](../ui/console-logic.html:233) seçili testnet çıkışlarını da “paper” diye adlandırabilir. **Etki:** görseller ve adlar gerçek kaynağı/ortamı yanlış temsil eder. **Öneri:** ölçüm ve ortam verisine bağlama; tarihi ölçüme run/tarih/kaynak; bilinmeyene `—`. **Kapanış:** farklı doluluk/koşu/pozisyon sayısında ekran değişmeli; testnet adı doğru olmalı.

### EP19 — Orta — Bilinmeyen net değerler özetlerde sıfır sayılıyor

**Kanıt:** [history:22](../fbot/api/history.py:22) null neti `0.0`, [66](../fbot/api/history.py:66) equity'de sıfır kabul eder; grup `n` tüm satırları sayar. Buna karşılık [paper_summary:16](../scripts/paper_summary.py:16) null netli kapanışları dışlar. **Doğrulandı:** aynı DB için özetlerin örneklem sözleşmesi farklı. **Koşula bağlı etki:** eski/eksik kayıtta kazanma oranı ve ortalama net aşağı çekilir; bilinmeyen sonuç sıfır sonuç sanılır. **Öneri:** toplam/bilinen/eksik işlem adetleri ve yalnız bilinen sonuçlarla hesap; kısmi USDT toplamını etiketle. **Kapanış:** pozitif, negatif ve null netli karışık veriyle iki ekranın tutarlı özeti.

### EP20 — Orta — Test kapsamı endpoint tüketimini ve gerçek render'ı korumuyor

**Kanıt:** [test_ui_build.py:1](../tests/test_ui_build.py:1) JS motoru olmadığını açıkça belirtir; testler yapısal. Altı kontrol geçtiği halde EP01/EP02/EP06/EP08 sabit/veri alanı sorunları mevcut. **Doğrulandı:** başarılı build kontrolü semantik uyumu kanıtlamıyor. **Öneri:** gerçek handler yanıtını render eden tarayıcı sözleşme testleri; null/eksik alan, 401/500, farklı run, ters yanıt sırası, farklı veriyle değişen kartlar. **Kapanış:** bu bulguları yakalayan kontrollerin CI'da çalışması; mock veri fixture olarak açıkça ayrılmalı.

## Statik olan her bilgi sahte değildir

| Sınıf | Örnek | Değerlendirme |
|---|---|---|
| Gerçek kayıt/veri | Universe fiyatları, OHLCV, DB pozisyon/kararları, heartbeat | Veri kaynağı var; yine run/ortam/zaman damgası doğru yorumlanmalı |
| Gerçek ama offline | `latency`, `research`, `replay_cmp`, `determinism` | Dosyadan okunur; canlı telemetri değildir. Faz 0 etiketi olan gecikme kartı doğru ayrım yapıyor; K5 kullanımında aynı ayrım yok. |
| Meşru sabit açıklama | S0–S4 adları, renkler, hipotez metinleri, kilitli karar kataloğu | Ölçüm iddiası değildir; etkin davranış değişirse açıklama da güncellenmeli |
| Açık eksik veri | `—`, “ölçülmedi”, “borsada doğrulanmadı” | Bilinmeyeni dürüstçe gösterir; örnek sayı sayılmaz |
| Simülasyon/başlangıç config'i | Paper modu; `paper-demo.toml` SL/TP değerleri | Simülasyon olması fiyatların uydurma olduğu anlamına gelmez. Demo eşikleri config'te ölçülmemiş makine testi değeri olarak etiketli. |
| Tasarım demosu | `ui/design/fbot Console.dc.html` içindeki demo JavaScript | Normal index build'ine alınmıyor; tasarım şablonunun sabit HTML'i ise alınıyor. Statik sunucu design dizinini de kapsar; dış erişim sınırı doğrulanmadı. |
| Yanıltıcı sabit gösterim | Performans yüzdeleri, SHA ✓, hash, disk barı, olumlu sağlık varsayımları | EP01–EP20 kapsamında düzeltme gerektirir |

## BU FAZDA YAPILMAYANLAR

- Uygulama kodu, testler, config veya runtime verisi değiştirilmedi; yalnız bu rapor, iki envanter ve TODO kaydedildi.
- Gerçek kill/reset/anahtar yazma isteği, emir, servis yeniden başlatma, kurulum, commit veya dağıtım yapılmadı.
- Tam pytest/determinizm paketi çalıştırılmadı; dosya oluşturan fixture'lar kullanılmadı. Mevcut altı salt okunur UI kontrolü ve bellekte handler denetimiyle sınırlı kalındı.
- Tarayıcı render'ı, görsel ekranlar, proxy/TLS/Basic Auth katmanı ve diğer canlı GET yolları uçtan uca doğrulanmadı. Node/NodeJS çalıştırıcısı PATH'te bulunmadı.
- Binance dış API sözleşmesi, gerçek hesap yetkileri, anahtar hot-reload ve ticaret performansı doğrulanmadı. Gizli anahtar/token okunup rapora yazılmadı.

Envanterler: [backend](backend-endpoint-envanteri-2026-09-12.md), [frontend](frontend-endpoint-envanteri-2026-09-12.md). Takip: [TODO](../TODO.md).
