# CLAUDE.md — fbot

Bu dosya her oturumun başında okunur. Kısa tutulur. Detay burada değil, `docs/` altındadır.

**Bu dosyayı her faz sonunda güncelle.** Değişen komutlar, yeni kısıtlar ve kapanan fazlar buraya yansır.

---

## PROJE

`fbot` — Binance USDⓈ-M Futures üzerinde çalışan, event-driven, piyasa-durumu farkındalıklı otomatik işlem sistemi.

Birincil hedef: **açık pozisyonu kârda kapatmak.** Giriş sinyali ikincil önceliktedir.

Tek başarı ölçütü: **maliyetler düşüldükten sonra pozitif net beklenti.** Kod hacmi, mimari zarafeti veya sinyal doğruluğu başarı ölçütü değildir.

Dil: Türkçe. Teknik olarak kesin ve doğrudan yaz.

---

## OTURUM BAŞI KONTROL LİSTESİ

1. `docs/PHASE.md` — hangi fazdayız, kapı açıldı mı?
2. `docs/decisions/` — son ADR'ler
3. `docs/latency-baseline.md` — ölçüm sonuçları (Faz 0 sonrası)
4. Bu dosyanın YASAKLAR bölümü

Aktif fazın dışında iş yapma.

---

## MUTLAK KURALLAR

**Uydurma yok.** Binance API endpoint, parametre, alan, stream adı, hata kodu ve rate limit değerlerini hafızadan yazma. Her birini `developers.binance.com` üzerindeki güncel dokümandan doğrula. Eğitim verisi eskimiş; Binance 2026'da WebSocket URL yapısını ve user data stream mekanizmasını değiştirdi. Doğrulayamadığını kullanma, sor.

**Belirsizlikte dur.** Gereksinim belirsizse veya iki gereksinim çelişiyorsa tahmin etme. Dur, net soru sor, cevabı bekle.

**Ölçmeden karar verme.** Gecikme, throughput, maliyet, kârlılık hakkında hiçbir sayı varsayımla belirlenmez. Ölçüm yoksa parametre sabitlenmez, "bilinmiyor" olarak işaretlenir.

**Yapmadıklarını beyan et.** Her teslimin sonunda `BU FAZDA YAPILMAYANLAR` başlığı ile eksikleri listele. Sessizce atlama.

**Hacim değil doğruluk.** Az sayıda doğru, test edilmiş, çalışan dosya. "Production quality" talimatını dosya sayısı olarak yorumlama.

**Karar günlüğü.** Her mimari karar `docs/decisions/NNNN-baslik.md` olarak ADR'ye yazılır: bağlam, seçenekler, seçim, gerekçe, sonuçlar. Karar değişirse eski ADR silinmez, üstüne yeni ADR yazılır.

---

## ONAY GEREKTİRENLER

Şunları yapmadan önce sor:

- Canlı emir gönderen kod yolunu aktif etmek
- API anahtarı isteyen herhangi bir işlem
- Sistem seviyesi kurulum (systemd, docker daemon, firewall, paket kurulumu)
- Veri silen işlemler
- Faz atlama veya faz kapısını kendi kendine açma
- Yeni bağımlılık eklemek
- Kilitli kararlardan sapmak

---

## KİLİTLİ KARARLAR

Bunlar tartışılmış ve karara bağlanmıştır. İtirazın varsa yaz, onay almadan uygulama.

| Konu | Karar |
|---|---|
| Piyasa | Binance USDⓈ-M Futures. Spot yok, spot abstraction'ı yazılmaz. |
| Pozisyon modu | One-way mode. |
| Sembol evreni | En fazla 20. Başlangıç TOP 10: 24 s USDT hacmi, stablecoin çiftleri hariç, günlük 00:00 UTC yenileme (ADR 0004). |
| Eşzamanlı pozisyon | En fazla 5. Sert limit, Risk Engine uygular. |
| Kaldıraç | BTCUSDT/ETHUSDT 10x, diğerleri 5x; config'den sembol başına. PnL notional üzerinden, ROE teminat üzerinden (ADR 0004). |
| Günlük işlem sayısı | Sert limit yok. Maliyet sürüklenmesi ölçülür ve alarm üretir. |
| Emir yolu | WebSocket API + Ed25519. REST yalnızca fallback / snapshot / mutabakat. |
| Kimlik doğrulama | Emir yolu: `session.logon` (Ed25519). User data: `userDataStream.start` + listenKey, keepalive private bağlantı yöneticisinin parçası (30 dk), `listenKeyExpired` → yeniden bağlan + mutabakat (ADR 0003). |
| Tax Report API | Kapsam dışı. Kullanılmaz. |
| Hot path | Tek process, tek thread. Event bus hot path'te yok. |
| Determinizm | Rule Zero zorunlu. |
| İşlem büyüklüğü | Her işlem **80 USDT notional**; miktar step'e aşağı yuvarlanır, filtre altı → REJECT (ADR 0004). |
| Açılışta koruma | Giriş dolunca SL + TP algo emirleri (`closePosition=true`), deterministik `clientAlgoId`. Mesafeler Faz 3'e kadar `null`, değer yoksa pozisyon açılmaz (ADR 0004). |
| Varsayılan mod | Paper. Canlı mod bilinçli ve açık bir işlemle etkinleştirilmedikçe çalışmaz. |

---

## RULE ZERO — DETERMİNİZM

Aynı kayıtlı veri iki kez oynatıldığında **bit-eşit karar dizisi** üretilmek zorundadır. Backtest güvenilirliğinin tek garantisi budur.

1. **Tek sıralama noktası.** Gateway tüm stream'leri tek toplam sıralı akışa dizer, monoton artan sequence verir.
2. **Mantıksal saat.** İş mantığı sistem saatini okumaz. `Clock` enjekte edilir: canlıda gerçek saat, replay'de event zamanı.
3. **Saf çekirdek.** İş mantığı `(state, event) -> (new_state, commands)` saf fonksiyonudur. I/O yok, log yazımı yok, ağ yok. Yan etkiler dışarıda uygulanır.
4. **Tek thread.** Deterministik çekirdek tek thread'te koşar. Eşzamanlılık yalnızca I/O kenarlarında.
5. **Seed'li rastlantı.** Slippage simülasyonu dahil her rastlantı seed'lidir, seed config'e yazılır.

CI'da determinizm testi çalışır. Kırılırsa merge yok.

---

## MİMARİ ÖZETİ

```
PROCESS 1 — trader (tek thread, tek async loop)
    WS bağlantıları (public / market / private — ayrı ayrı)
      P0 → Position Monitor → Exit Rules → Risk Gate → Order Sender (WS API)
      P2 → Feature Engine → Market State → Decision Engine
      → bus'a fire-and-forget yayın

PROCESS 2 recorder | PROCESS 3 persistence | PROCESS 4 api/metrics
```

- **Fast Path (P0):** açık pozisyonu yönetir. Yeni pozisyon açma kararı bu yolda değildir.
- **Analytics Path (P2):** yeni giriş fırsatını değerlendirir.
- Bir modül, işi için gerek duymadığı başka bir modülün sonucunu beklemez.
- Fast path'te hiçbir senkron iş 1 ms'yi geçmez. Loop lag ölçülür ve yayınlanır.
- Veritabanı hot path'te yoktur. Aktif pozisyon state'i bellektedir.
- Paralellik sembol shard'ıyla sağlanır, thread ile değil.

**Fiyat referansları ayrı ayrı tanımlıdır:** `trigger_price_source`, `pnl_accounting_source`, `execution_price_estimate`. Tek bir "fiyat" kavramı kullanma.

---

## MALİYET MODELİ

Maliyet **her PnL hesabına, her backtest'e, her karar eşiğine** dahildir. Maliyetsiz hiçbir sonuç raporlanmaz.

Bileşenler: komisyon (maker/taker ayrı, BNB indirimi opsiyonu), funding, slippage (defter derinliğinden tahmin, sabit varsayım değil).

Oranlar config'den gelir, hard-code edilmez.

**PnL gerçeği iç hesap değil, Binance'ın income kayıtlarıdır.** Gerçekleşen PnL, komisyon ve funding kalemleri çekilir, iç muhasebeyle mutabakat yapılır, sapmada alarm üretilir.

Sürekli ölçülen: komisyon/brüt kâr oranı, toplam maliyet/sermaye oranı, işlem başına ortalama net sonuç. Eşik aşımında alarm (işlem engellenmez).

---

## KORUMA KATMANLARI

Üç bağımsız katman, hiçbiri diğerinin yerine geçmez.

1. **Borsa tarafı koruma.** Pozisyon açılır açılmaz koşullu koruma emri borsaya yerleştirilir (`closePosition=true`). Sistem çökse bile durur.
2. **Uygulama tarafı akıllı çıkış.** Piyasa durumu bozulmasına dayalı. Her zaman `reduceOnly=true`.
3. **Kalıcı kill switch.** Restart'ı hayatta kalır, elle sıfırlanmadan açılmaz.

**Yarış durumu:** borsa stop'u tetiklenirken uygulama da kapatma gönderirse ters pozisyon açılır. `closePosition` + `reduceOnly` semantiği ve tek sahiplik kuralıyla engellenir. Bir pozisyonun koruma emirlerini yalnızca tek bileşen yönetir; her emir için deterministik `clientOrderId`.

**Auto-cancel (countdownCancelAll) emirleri iptal eder, pozisyonu kapatmaz.** Koruma emirlerine **asla** uygulanmaz, yalnızca giriş emirlerine. Bunu "kill switch" diye sunma.

**Açılışta mutabakat:** borsa tek doğruluk kaynağıdır. Açık pozisyon ve emirler borsadan çekilir, iç state ile karşılaştırılır, uyuşmazlıkta trading kilitlenir.

**Isınma:** restart sonrası feature pencereleri dolana kadar işlem açılmaz.

**Bayatlık:** her WS kategorisi ayrı izlenir. Eşik aşımında yeni pozisyon durur.

---

## KOD KONVANSİYONLARI

- Python. Rust yalnızca ölçülmüş darboğaz + onay ile.
- Bağımlılıklar izole ortamda. Sistem Python'ı kirletilmez.
- Saf çekirdek ile I/O kenarları dosya seviyesinde ayrıdır. Çekirdek modüllerinde `import` seviyesinde ağ/DB/dosya bağımlılığı bulunmaz.
- Her karar ve işlem şu damgaları taşır: config sürümü, git commit SHA, correlation id.
- Tüm eşikler ve parametreler config'dedir. Hard-code edilmiş eşik = hata.
- Test önce yazılır.
- `LiveExecutionAdapter` onay alınana kadar korumalı stub kalır. Yarım implementasyon, hiç implementasyondan tehlikelidir.

## GÜVENLİK

- API anahtarı asla kod, repo, log veya image içinde bulunmaz.
- `.env` gitignore'da; repoda yalnızca `.env.example`.
- Binance anahtarında çekim yetkisi **kapalı**, IP whitelist **açık**. Doğrulanmadan canlı moda geçilmez.

---

## KOMUTLAR

> Faz ilerledikçe doldur. Var olmayan komutu buraya yazma.

```bash
# kurulum
make setup

# testler
make test              # birim (51 test)

# Faz 0 ölçüm
make measure-latency RUN=<run_id>    # 24 saat, 4 process, nohup
make summarize-latency RUN=<run_id>
make unit-economics                  # docs/unit-economics.generated.md

# Faz 1 kayıt
make up REC=<run_id> / make down / make logs
make verify-recording REC=<run_id>
make verify-orderbook REC=<run_id> MAXF=2

# (Faz 2+ ile gelecek: run-paper, replay)
```

---

## FAZ DURUMU

> Tek doğruluk kaynağı `docs/PHASE.md`. Burası özet.

| Faz | Konu | Durum |
|---|---|---|
| 0 | Ölçüm, build-vs-buy, unit economics | **AKTİF** (2026-09-10) |
| 1 | Temel + ham veri kaydı | Faz 0 kapısı bekliyor (24 s ölçüm) |
| 2 | Deterministik çekirdek + replay | — |
| 3 | Offline araştırma (**DUR kapısı**) | — |
| 4 | Pozisyon yönetimi ve çıkış | — |
| 5 | Risk Engine | — |
| 6 | Giriş mantığı | — |
| 7 | Paper trading (min 4 hafta) | — |
| 8 | Gözlemlenebilirlik | — |
| 9 | Testnet canlı execution | — |
| 10 | Küçük sermaye ile canlı | — |

**Faz 3 bir dur kapısıdır.** Kayıtlı veri üzerinde tanımlanan piyasa durumlarının hiçbiri maliyetleri aşan beklenti üretmiyorsa kod yazmayı bırak ve bildir.

Her faz teslim sırası: hedef → **kabul kriterleri** → ADR → dosya ağacı → **testler** → kod → docker → config → README → çalıştırma komutları ve çıktıları → yapılmayanlar listesi.

---

## YASAKLAR

- Kârlılık varsaymak
- Doğrulanmamış API detayı kullanmak
- Ölçülmemiş performans iddiası
- Look-ahead bias — feature hesaplarına gelecek veri sızması
- Maliyetsiz sonuç raporlamak
- Faz atlamak veya kendi kapısını kendi açmak
- Yarım implementasyonu canlı yola bağlamak
- API anahtarını repoya, log'a, image'a yazmak
- Ölçülmüş darboğaz olmadan Rust'a geçmek
- Hot path'e ağ hop'u eklemek
- Fast path'te thread kullanmak
- Ağırlıklı çok-faktörlü skorlamayı v1'e koymak (ağırlık = serbest parametre = overfit)
- Market State'i 5 durumdan fazlaya çıkarmak
- Auto-cancel'ı koruma emirlerine uygulamak
- listenKey keepalive döngüsü yazmak
- Yüzlerce dosyalık iskelet üretmek
