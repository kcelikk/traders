# TODO

## Endpoint uyumu ve frontend veri doğruluğu — 2026-09-12

Kaynak: [inceleme raporu](docs/endpoint-uyum-ve-statik-veri-raporu-2026-09-12.md). Envanterler: [backend](docs/backend-endpoint-envanteri-2026-09-12.md), [frontend](docs/frontend-endpoint-envanteri-2026-09-12.md).

Bu liste yalnızca tespit ve öneri kaydıdır; aşağıdaki düzeltmeler uygulanmadı. **20 açık iş: 7 yüksek, 13 orta.** Kanıt, dosya/satır, etki ve ayrıntılı kapanış ölçütleri raporda aynı EP kimliğiyle bulunur.

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
