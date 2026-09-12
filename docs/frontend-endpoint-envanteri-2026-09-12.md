# Frontend endpoint envanteri

Tarih: 2026-09-12. İncelenen çalışma ağacının HEAD'i: `14782f7dfcc3`.

**6 farklı API işlemi, 5 farklı API yolu.** Frontend ayrı HTTP API sunmuyor; aşağıdaki envanter backend'e gönderdiği çağrıları gösterir.

Canlı giriş `ui/index.html`; kaynakları `ui/design/fbot Console.dc.html` içindeki şablon, `ui/console-logic.html`, `ui/keys-panel.html`, topoloji ve geçmiş panelleri. [build_ui.py](../scripts/build_ui.py:107) bunları birleştirir. Tasarım dosyasının demo JavaScript'i build'e alınmıyor; `<x-dc>` şablonundaki sabit metinler ise override edilmedikçe canlı HTML'e taşınıyor. Kaynak ve üretilen dosyadaki aynı çağrı iki endpoint sayılmadı.

## API çağrıları

| ID | Yöntem/yol | Tetikleyici / tekrar | İstek ve tüketilen yanıt | Kaynak / üretilmiş dosya | Uyum |
|---|---|---|---|---|---|
| FE01 | `GET /api/state[?run=…]` | Mount'ta ve 2 saniyede bir; başarılı kill/reset ardından tekrar | URL'deki `run` encode edilir. `universe, bars, recorder, freshness, config, paper, environments, kills, positions, open_positions, verdicts, fsm, exit_reasons, research, replay_cmp, determinism, latency` ve diğer ekran alanları | [poll](../ui/console-logic.html:38), [index](../ui/index.html:820) | Yol/yöntem uyumlu; alan, veri kökeni ve sabit gösterim eksikleri raporda |
| FE02 | `GET /api/history?limit=25&offset=N[&run=…]` | Geçmiş ekranına girişte ve sayfa değişiminde | `trades, total, performance, run_id, env, note`; backend `run_missing` döndürse de ayrı durum gösterilmiyor | [loadHistory](../ui/console-logic.html:44), [index](../ui/index.html:826) | Yol/yöntem/sorgu uyumlu; tazelik, yarış, maksimum DD kapsamı eksik |
| FE03 | `GET /api/keys` | Panel açılınca; testnet POST sonrası 5 saniyelik gecikmeyle en fazla 5 kontrol | `status`, `services`; servis `armed/age_s/reason` üzerinden gösterilir | [load](../ui/keys-panel.html:90), [index](../ui/index.html:1469) | Yol/yöntem uyumlu; HTTP hata yönetimi ve anahtar sürümü doğrulaması eksik |
| FE04 | `POST /api/kill` | Kill modalında onay | `{env: killEnv, reason: 'manual (konsol)'}`; başarıdan sonra state yeniden okunur | [confirmKill](../ui/console-logic.html:545), [index](../ui/index.html:1327) | Gövde/yol uyumlu; `killEnv` seçili/fallback koşunun ortamından türetilir |
| FE05 | `POST /api/kill/reset` | Aktif kill düğmesine basılınca | `{env: killEnv, note: 'konsol'}`; başarıdan sonra state yeniden okunur | [toggleKill](../ui/console-logic.html:543), [index](../ui/index.html:1325) | Gövde/yol uyumlu; reset için ayrıca modal yok |
| FE06 | `POST /api/keys` | Kaydet/etkinliği kaldır düğmeleri | `{env, armed: UTC tarih veya '', key?, secret?}`; `updated, note, status, error` okunur; `warning` okunmuyor | [kaydet](../ui/keys-panel.html:111), [index](../ui/index.html:1490) | Temel sözleşme uyumlu; backend sahiplik uyarısı görünmez |

Tüm API yolları göreli/same-origin. Ana istemci [req](../ui/console-logic.html:26) `X-Fbot-Token`, `cache: no-store`, JSON gövdesi varsa `Content-Type` kullanır; `r.ok` ve JSON geçerliliğini kontrol eder. Token `localStorage.fbot_token` içinde tutulur. Anahtar paneli kendi `fetch` zincirini kullanır ve aynı kontrolleri tam paylaşmaz.

Frontend `/api/health` çağırmıyor. Bu tek başına hata değildir: konsol state içindeki tazelikten besleniyor. WebSocket/SSE/axios istemcisi tespit edilmedi; ekrandaki “WebSocket” ifadeleri backend bağlantılarını anlatıyor.

## Ekran → endpoint / veri kaynağı

| Ekran | Endpoint | Başlıca veriler / sınır |
|---|---|---|
| Durum | state | Recorder piyasa görünümü + seçili koşu özeti; tek veri kaynağı değil |
| Pozisyonlar | state | Açık/son pozisyonlar, FSM, çıkış nedenleri, pozisyon config'i; replay kutularında sabit rakamlar var |
| Risk Engine | state; kill/reset POST | Config + recorder tazelik/beta/skew + koşu heartbeat/ret geçmişi; güncel risk kararıyla birebir değil |
| Algoritma & sinyal | state | Feature/durum/verdict; D1/D2/D3 ve pipeline'ın bir kısmı sabit açıklama |
| Piyasa durumu | state | Universe/transitions; `allowed_cells boş` sabit |
| Replay & araştırma | state | Offline `research`, `replay_cmp`, `determinism`; raporlar run seçimiyle değişmez |
| Kayıt | state | Recorder sayaçları/dosyalar; eksik `recorder.frames`, sabit SHA ve disk göstergeleri |
| Geçmiş & performans | history | Sayfalı kapanışlar, tüm kapanışların grup özetleri, son 500 equity kaydı |
| Topoloji | state | Kısmen heartbeat, kısmen sabit mimari metin ve varsayılan canlılık |
| Config | state | Koşu config'i + repo config'i + sabit kilitli kararlar |
| API anahtarları | keys GET/POST | Maskeli tanımlılık/silahlanma; secret geri okunmaz |

`/status` gibi ekran açıklamaları HTTP endpoint değildir. Ekran geçişleri `state.screen` ile yapılır; `goRun()` `location.search` değiştirerek sayfayı yeniden yükler. `LIVE` yazan düğme **testnet** koşusunu seçer ([index](../ui/index.html:72), [setLive](../ui/console-logic.html:533)).

## API dışı tarayıcı istekleri

| Kaynak | Hedef | Not |
|---|---|---|
| Sayfa yükleme / koşu seçimi | `/`, `/index.html`, mevcut yol + `?run=…` | HTML navigasyonu |
| HTML | `./support.js` | Runtime |
| `window.__resources` eşlemesi | `./vendor/react.production.min.js`, `./vendor/react-dom.production.min.js`, `./vendor/babel.min.js` | Kodda unpkg URL'leri bulunur; normal index build'i bunları yerel dosyalara eşler |
| HTML stylesheet | `fonts.googleapis.com/css2?...` | Google Fonts; dönen CSS'nin font dosyalarına bağımlılık; ağdan yüklenmesi bu incelemede ölçülmedi |
| Runtime genel yükleyicileri | `fetch(location.href)`, `fetch(url)`, `fetch(target)` | [support.js](../ui/support.js:159), [1206](../ui/support.js:1206), [1651](../ui/support.js:1651); genel kaynak/içe aktarma mekanizması, ek fbot API endpoint'i değil. `location.href` tekrar fetch'i `window.__resources` yoksa çalışır. |

## Alan uyumunun sınırları

- `recorder.frames` frontend'de okunuyor ama backend snapshot'ında yok; sayaçlar `—` kalır.
- `warning` anahtar yazma yanıtında var ama arayüzde gösterilmiyor.
- Anahtarın uygulandığını kanıtlayacak bir sürüm alanı iki tarafta da yok; taze heartbeat bunu tek başına kanıtlamaz.
- Testnet heartbeat `exit_mode`, `breaker`, `execution`, `persist`, `telemetry`, `shadow_intents` taşıyabiliyor; arayüz bunları yeterince kullanmıyor. Ayrı endpoint eksikliği değil, mevcut verinin görünüm eksikliğidir.
- `paper.env` yerine üst seviye `mode` kullanılmıyor; bu doğru, çünkü `mode` backend'de sabit paper.

`python3 -B -m scripts.build_ui --check` sonucu **güncel**. Mevcut altı UI yapı kontrolü dosya yazmadan doğrudan çağrıldı ve geçti. Tarayıcı/DOM çalıştırması yapılmadığından bu sonuç JavaScript çalışma zamanı veya görsel doğrulama sayılmaz.

İlişkili belgeler: [backend envanteri](backend-endpoint-envanteri-2026-09-12.md), [bulgular](endpoint-uyum-ve-statik-veri-raporu-2026-09-12.md), [TODO](../TODO.md).
