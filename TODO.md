# TODO

## Endpoint uyumu ve frontend veri doğruluğu — 2026-09-12

Kaynak: [inceleme raporu](docs/endpoint-uyum-ve-statik-veri-raporu-2026-09-12.md). Envanterler: [backend](docs/backend-endpoint-envanteri-2026-09-12.md), [frontend](docs/frontend-endpoint-envanteri-2026-09-12.md).

Bu liste yalnızca tespit ve öneri kaydıdır; aşağıdaki düzeltmeler uygulanmadı. **20 açık iş: 7 yüksek, 13 orta.** Faz ve gate açık işleri için aşağıdaki ikinci bölüme bak. Kanıt, dosya/satır, etki ve ayrıntılı kapanış ölçütleri raporda aynı EP kimliğiyle bulunur.

- [ ] **EP01 / Yüksek:** Sabit replay performans yüzdelerini rapor verisine bağla; veri yokken ölçülmedi göster. Kapanış: farklı/eksik raporla kart testi.
- [ ] **EP02 / Yüksek:** Dosya bazlı doğrulama sonucu olmadan `SHA ✓` gösterme; koşu satırlarına dosya doğrulama rozeti basma. Kapanış: bozuk/doğrulanmamış dosya testleri.
- [ ] **EP03 / Yüksek:** Risk tablosunu seçili trader'ın güncel risk girdileri/sonucuyla besle; recorder, geçmiş ret ve bilinmeyen değerleri ayır. Kapanış: limit aşımı ve bayat/eksik veri senaryoları.
- [ ] **EP04 / Yüksek:** `cost_drift` sabit sermaye/notional/komisyon/funding/slippage varsayımlarını gerçek kayda ve koşu config'ine bağla; eksik maliyeti etiketle. Kapanış: değişken maliyetli referans veri.
- [ ] **EP05 / Yüksek:** Anahtar değişiminde credential sürümü + applied_at + hedef armed onayı ekle; eski heartbeat yeni anahtarı onaylamasın. Kapanış: arm/disarm/ertelenmiş değişim senaryoları.
- [ ] **EP06 / Orta:** Statik git/config hash'lerini doğru recorder/trader kimlik alanlarından göster. Kapanış: run değişimi ve eksik kimlik kontrolü.
- [ ] **EP07 / Orta:** D1/D2/D3, pipeline, allowed_cells, yaş sınırı, SL/TP ve intent açıklamalarını etkin config/verdict'e bağla. Kapanış: dolu/boş hücre ve değişen parametrelerle tutarlılık.
- [ ] **EP08 / Orta:** `recorder.frames` üretici/tüketici sözleşmesini tamamla; kategori ve tekil akış adetlerini açık adlandır. Kapanış: bilinen kaydın sayaçları.
- [ ] **EP09 / Yüksek:** Eksik `run` için state/history/drift davranışını birleştir; başka koşuya sessiz fallback ve onun kill/reset kontrolünü engelle. Kapanış: olmayan run senaryosu.
- [ ] **EP10 / Yüksek:** Kill/FROZEN/mutabakat metinlerini ADR 0021 ve `exit_mode` ile uyumlu yap. Kapanış: FULL/PROTECTION_ONLY/HALTED ve kill gösterimleri.
- [ ] **EP11 / Orta:** Anahtar panelinde ortak HTTP hata yönetimi ve `warning` gösterimi kullan; başarısız GET'te eski durumu işaretle. Kapanış: 401/500/non-JSON/200+warning.
- [ ] **EP12 / Orta:** Poll/geçmiş yanıtlarında sıra/iptal/timeout ve güncellik yönetimi; açık geçmiş ekranını yenile. Kapanış: ters yanıt sırası, bağlantı kesintisi, yeni kapanış.
- [ ] **EP13 / Orta:** MAKS DD'yi tüm koşudan hesapla veya son 500 kapsamını açıkça göster. Kapanış: erken zirve/düşüş içeren >500 kayıt.
- [ ] **EP14 / Orta:** Tam pathname eşleştirmesi ve tutarlı JSON 404/405 politikası ekle. Kapanış: son ek, query, slash, bilinmeyen yol/yöntem matrisi.
- [ ] **EP15 / Orta:** POST JSON/gövde tipi/boyut/alan doğrulaması ve kontrollü 400/413 yanıtı ekle. Kapanış: bozuk JSON, null/dizi ve boyut sınırları.
- [ ] **EP16 / Orta:** Topoloji ve private göstergelerini rol bazlı taze sağlık verisine bağla; unknown durumunu koru; breaker/execution/telemetry görünümünü tamamla. Kapanış: eksik/bayat heartbeat ve farklı stream profilleri.
- [ ] **EP17 / Orta:** Kaldıraç/ROE/notional/tick gösterimlerini etkin ve doğrulanmış veriye bağla; bilinmeyen kaldıraçla kesin ROE verme. Kapanış: farklı ayarlarla hesap ve başlık testi.
- [ ] **EP18 / Orta:** Sabit disk oranı/hızı, orderbook replay sonuçları, 0/5, pozisyon yok, LIVE/testnet ve çıkış kaynağı etiketlerini düzelt. Kapanış: farklı veri/ortamla değişen doğru gösterim.
- [ ] **EP19 / Orta:** Null net sonuçlarını sıfırdan ayır; bilinen/eksik işlem sayısı ve kısmi USDT toplamı göster; iki özetin örneklemini tutarlı yap. Kapanış: null/pozitif/negatif netli karışık veri.
- [ ] **EP20 / Orta:** Gerçek handler yanıtı ile tarayıcı render'ını doğrulayan sözleşme testleri ekle. Kapanış: eksik alan, farklı veri, HTTP hata ve istek yarışlarının CI'da denetlenmesi.

`GET /api/health` frontend'de kullanılmıyor; konsolun bunu kullanması zorunlu değildir. İzleme için kullanılacaksa `ok=true` değerinin yalnız sınırlı sunucu canlılığını anlattığı belgelenmeli; trader/veri tazeliği garantisi olarak kullanılmamalı.

---

## Faz ve gate açık işleri — 2026-09-12

Kaynak: `docs/PHASE.md`. Bu bölüm yalnız kayıttır; hiçbiri uygulanmadı. **7 onay kapısı, 9 açık
kalem, 4 açık faz.** Kapılar proje sahibi kararı olmadan açılmaz (CLAUDE.md ONAY GEREKTİRENLER).

### A. Proje sahibi kararı bekleyen kapılar (hepsi bugün kapalı)

- [ ] **GK01:** `[userdata] mode = "active"` — çekirdeğin borsa dolum olaylarını tüketmesi. Kod hazır, shadow'da çalışıyor; gözlem verisi yok (pozisyon açılmıyor). Kapanış: canlıda `order_ack/fill/done` tüketimi + mutabakat farkı sıfır.
- [ ] **GK02:** `[reconcile] orphan_cancel = "apply"` — sahipsiz koruma emrinin gerçekten iptali. Bugün `dry_run`, plan boş. Kapanış: yalnız bizim kimlik gramerimize uyan emirde iptal, doğrulama çağrısıyla.
- [ ] **GK03:** `[reconcile] protect_repair = "apply"` — korumasız pozisyona koruma emri konması. Kapanış: bilinen pozisyonda onarım + `-4130` ihlali yok (ADR 0023).
- [ ] **GK04:** `[reactors] mode = "active"` — olay-tetiklemeli çıkışın emir üretmesi. Bugün bilinçli yapılandırma hatası. Kapanış: re-baseline #2 + shadow gözlem verisi.
- [ ] **GK05:** `v1_state_cell` stratejisinin `paper_ok`'a terfisi. Paper kanıtı ister; bugün `replay_ok`, testnet'te kayıt defteri engelliyor.
- [ ] **GK06:** Mainnet **okuma** anahtarı — private WS biçimi, listenKey keepalive, pozisyon modu, çoklu varlık teminatı ve bakiye alanları para riski olmadan doğrulanır (`docs/mainnet-dogrulama.md` §4).
- [ ] **GK07:** Mainnet `-4130` doğrulaması — gerçek pozisyon gerektirir (~77 USDT notional / ~8 USDT teminat, birkaç saniye). Faz 10 açılmadı; ölçülmüş risk belgede.

### B. Kapanmış fazlarda açık kalan kalemler

- [ ] **AK01 / Faz 0:** Unit economics üç girdi (tutma süresi, işlem sayısı, hedef hareket) proje sahibinden gelmedi. Engellediği: başabaş kazanma oranı hedefi yok.
- [ ] **AK02 / Faz 0:** Komisyon kademesi hesaptan teyit edilmedi (VIP0 üçüncü taraf kaynak). Engellediği: tüm maliyet hesapları bu varsayıma dayanıyor.
- [ ] **AK03 / Faz 0:** Slippage dağılımı ölçülmedi; kayıt depth akışı bu amaçla işlenmedi. Engellediği: `slippage_max_bps` kapalı, K15 "ölçülmedi".
- [ ] **AK04 / Faz 3:** Canlı kayıt üzerinde ≥3 günlük nihai rapor yok; karar 32 günlük arşivle verildi (ADR 0009). Kapanış: kendi verimizle doğrulama.
- [ ] **AK05 / Faz 4:** `clientAlgoId`/`clientOrderId` uzunluğu gerçek borsada doğrulanmadı. Not: `-4015` Gate 2'de kapandı, borsa teyidi ayrı.
- [ ] **AK06 / Maliyet kuralı:** Binance income kayıtlarıyla PnL mutabakatı. `TestnetClient.income()` yazıldı, hiç çağrılmıyor. CLAUDE.md: PnL gerçeği iç hesap değil income kayıtlarıdır.
- [ ] **AK07 / Faz 9:** Testnet hesabındaki bize ait olmayan iki koruma emri (BTCUSDT, 2026-05, `algoStatus=NEW`, `algo_orphan`). **Testnet trading kilitli** (K2 REJECT); iptal borsada değişiklik → onay bekliyor. GK02 ile birlikte ele alınır.
- [ ] **AK08 / Faz 3:** Gate 3 bulgusu — testnet hesabı çoklu varlık teminat modunda; `availableBalance` USDT dışını da içeriyor. Mainnet hesabının modu proje sahibi kararı.
- [ ] **AK09 / Gate 4:** Devre kesici eşikleri ölçülmedi, seçildi. Kapanış: `alarm` modunda yanlış-pozitif oranı ölçülünce sabitlenir.

### C. Açık fazlar

- [ ] **FZ07 / Faz 7 paper trading:** Servis ayakta, karar üretmiyor. Bekleyen: ölçülmüş giriş kuralı (`allowed_cells` boş). Hedef: 2 hafta ara rapor, 4 hafta.
- [ ] **FZ08 / Faz 8 gözlemlenebilirlik:** Konsol var; metrik toplayıcı ve alarm kanalı yok. Prometheus/Grafana veya eşdeğeri. **Stratejiden bağımsız ilerleyebilir.**
- [ ] **FZ09 / Faz 9 testnet:** Silahlı, borsa erişimi doğrulandı, emir göndermedi. "2 hafta hatasız" saati başlamadı. Bekleyen: giriş kuralı + AK07.
- [ ] **FZ10 / Faz 10 küçük sermaye canlı:** Bekliyor. `LiveExecutionAdapter` korumalı stub. Bekleyen: Faz 9 sonucu + proje sahibi onayı.

### D. Ölçülemeyenler — tek nedeni `allowed_cells` boş, pozisyon açılmıyor

- [ ] **OL01:** Reactor shadow gözlemi (bir hafta karşılaştırma planlanmıştı).
- [ ] **OL02:** Devre kesicinin yanlış-pozitif oranı (bkz. AK09).
- [ ] **OL03:** Telemetri histogramları canlıda boş.
- [ ] **OL04:** Strateji × versiyon bazında PnL atfı, sembol kirası çakışma sayısı.
- [ ] **OL05:** Dolum çerçevesinden çekirdeğe gecikme, yinelenen `tradeId` sayısı.

### E. Strateji arayışı (ADR 0010: kârlılık gösterilmedi)

- [ ] **ST01:** H5 reddedildi (`docs/research/strateji-v1.md`, 320 birleşim, 0 geçen). B yolu açık: bu fazda hiç kullanılmamış veri — `forceOrder` likidasyon kaskadları, `depth` dengesizliği, funding uçları — üzerine yeni hipotez döngüsü. Ön kayıtlı hipotez + karar kuralı **ölçümden önce** yazılır.
- [ ] **ST02:** Tesisat testi için kâr beklentisi **olmayan**, açıkça öyle etiketlenmiş bir giriş kuralı (ADR 0015). Araştırmadaki en dengeli çıkış karışımı: stop 0,5 / hedef 0,6 / tutma 60 dk (hedef %24,1 · stop %30,2 · süre %45,7). Bu ayrı bir onay kararıdır.
