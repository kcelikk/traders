# ADR 0001 — Build vs buy

Tarih: 2026-09-10 · Durum: **öneri, proje sahibi onayı bekliyor**

## Bağlam

Faz 1'den önce mevcut açık kaynak platformların bizim kilitli kararlarımızla (Rule Zero determinizm, tek thread hot path, bus'sız fast path, saf çekirdek, WS API + Ed25519, algo koşullu emirler, kategori bazlı WS bağlantıları) uyumu değerlendirildi. Değerlendirme kaynak kod ve resmi doküman üzerinden yapıldı; kütüphane iddiaları hafızadan yazılmadı.

## Karşılaştırma

| Aday | Sürüm / son etkinlik | Futures WS bölünmesi (/public /market /private) | Ed25519 + ws-fapi | Algo (koşullu) emirler | Deterministik replay | Fast/analytics ayrımı | Lisans |
|---|---|---|---|---|---|---|---|
| **NautilusTrader** | 2.0.0rc4 (2026-09-02), stable 1.231 (2026-08-02) | Var: "Optional market WebSocket endpoint override", "Optional private stream override" (docs). Kaynak grep yapılamadı (GitHub code search kimlik istiyor). | Ed25519 önerilen, HMAC "deprecated", RSA desteklenmiyor | Var: STOP_MARKET, STOP_LIMIT, TAKE_PROFIT(_MARKET), TRAILING_STOP_MARKET algoOrder üzerinden; "Futures algo cancel may fall back … to the regular-order endpoint" | Event-driven, canlı ile aynı bileşenler; Rust backtest motoru; determinizm iddiası dokümanda açıkça alıntılanamadı | Kendi MessageBus / Actor / Strategy mimarisi; hot path bileşenleri bus üzerinden konuşur | LGPL-3.0 |
| **CCXT Pro** | 4.5.78 | Var: `getWsUrl(type, category)` futures için `prefix/<category>/ws` üretiyor; private `?listenKey=` | ws-fapi URL var; session.logon grep'te yok | REST `algoOrder` endpoint tanımları var | Yok | Yok; birleşik API Binance'e özgü semantiği (closePosition, algo, priceMatch, STP, rate-limit header) soyutlar | MIT |
| **Hummingbot** | constants dosyası 2026-06-11 | Var: `public/stream`, `market/stream`, `private/ws` | Yok (REST HMAC) | **Yok**: `algoOrder` sabiti yok → koşullu emirler eski endpoint'te **-4120** alır | Yok (canlı odaklı) | Market-making çerçevesi; tek WS bağlantı, throttler | Apache-2.0 |
| **Freqtrade** | aktif | CCXT'ye bağlı | CCXT'ye bağlı | CCXT'ye bağlı | Mum bazlı backtest; "inability to know how prices moved intra-candle"; futures'ta funding "backtests are inaccurate" | Strateji çerçevesi mum döngülü; P0/P2 ayrımı yok | GPL-3.0 |
| **binance-futures-connector-python** | v4.1.0, **2024-10-31** | Yok (release notlarında yok) | Yok | Yok | Yok | Yok | MIT |
| **python-binance** | issue #1683 (URL bölünmesi) 2026-06-08 "completed" | Var (kapatılmış issue) | Bilinmiyor | Bilinmiyor | Yok | Yok | MIT |

## Seçenekler

**A. NautilusTrader üzerine kur.**
Artı: en olgun aday; futures algo emirler, Ed25519, funding geçmişi, event-driven backtest hazır.
Eksi: (1) çekirdek Rust; hata ayıklama ve determinizm doğrulaması bizim Python kuralımızın dışında bir katmanda olur. (2) 2.0.0 rc aşamasında, API oynak. (3) Kendi MessageBus/Actor mimarisi hot path'te bus'sız saf-çekirdek kararımızla çelişir; uyarlamak framework'e karşı savaşmak demektir. (4) LGPL-3.0. (5) Rule Zero'nun temeli olan "gateway tek sıralama noktası + ham kayıt = replay girdisi" Nautilus'un data catalog modeliyle örtüşmez; bit-eşitliği kendi testimizle yine kanıtlamamız gerekir.

**B. CCXT Pro'yu bağlantı katmanı olarak kullan, çekirdeği kendimiz yaz.**
Artı: URL bölünmesi ve algo endpoint'leri mevcut; MIT.
Eksi: Kontrol etmek zorunda olduğumuz tam o ayrıntıları soyutlar: closePosition/algo semantiği, priceMatch, STP, rate-limit header senkronizasyonu, 503 UNKNOWN davranışı, session.logon. Her birini soyutlamanın altından delmek gerekir; kütüphane değeri kalmaz.

**C. Sıfırdan, ince yüzey.**
İhtiyaç duyulan yüzey dar: 2 market kategorisi + 1 private stream bağlantısı, ws-fapi'de `session.logon`, `order.place`, `order.modify`, `order.cancel`, `algoOrder.place`, `algoOrder.cancel`, REST'te snapshot/mutabakat/income (≈10 endpoint). Bağımlılık: `websockets` + stdlib.
Artı: Rule Zero, tek thread, saf çekirdek doğrudan tasarlanır; her API ayrıntısı dokümandan doğrulanmış tek yerde durur; Python.
Eksi: Backtest/replay altyapısı bizde (Faz 2). Geliştirme süresi ölçülmedi.

## Seçim

**C.** Gerekçe: projenin ayırt edici gereksinimi bir strateji çerçevesi değil, deterministik replay ve fail-safe pozisyon yönetimidir. Bu ikisi mevcut platformlarda ya yok (CCXT, Hummingbot, connector) ya da bizim mimari kurallarımızla çelişen bir çerçeveye gömülü (Nautilus). Borsa yüzeyi dar olduğu için "buy" kazancı küçük, "buy" maliyeti (soyutlama altını delme, framework'e karşı savaşma) büyük.

NautilusTrader **referans** olarak kullanılacak: algo cancel fallback davranışı, Ed25519 imza akışı ve fill-model tasarımı Faz 2 ve Faz 9'da karşılaştırma kaynağı.

## Sonuçlar

- Faz 1 gateway: `websockets` üzerinde kategori başına bağlantı, tek sıralama noktası, ham JSONL/gzip kayıt.
- Faz 2: replay harness ve maliyet modeli bizde.
- Yeniden değerlendirme noktası: Faz 3 kapısı. Araştırma bir backtest çerçevesine ihtiyaç duyarsa ve replay harness yetmezse bu ADR üstüne yenisi yazılır.
- Bilinmeyen: geliştirme süresi. Ölçülmedi; tahmin verilmiyor.
