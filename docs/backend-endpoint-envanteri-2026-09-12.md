# Backend endpoint envanteri

Tarih: 2026-09-12. İncelenen çalışma ağacının HEAD'i: `14782f7dfcc3`.

Kapsam: frontend'e hizmet veren uygulama sunucusunun **gelen HTTP arayüzü**. Binance'a giden gateway istekleri ayrı bir entegrasyon sınırıdır; bu envanter onların Binance dokümantasyonuna uygunluğunu doğrulamaz. Kaynak: [server.py](../fbot/api/server.py:372). Sunucu `SimpleHTTPRequestHandler` üzerinde kuruludur; framework router/OpenAPI şeması bulunmuyor.

**7 API işlemi, 6 farklı API yolu: 4 GET + 3 POST.** Varsayılan adres `127.0.0.1:8787`; bind, port ve UI dizini CLI/ortam ayarlarıyla değişebilir ([server.py](../fbot/api/server.py:463)).

## API işlemleri

| ID | Yöntem ve yol | Girdi | Başarı yanıtı / kaynak | Hata ve yan etki | Frontend tüketicisi |
|---|---|---|---|---|---|
| BE01 | `GET /api/state` | İsteğe bağlı `run` sorgusu | Birleşik konsol snapshot'ı; kayıt tail'i + koşu SQLite'ı + TOML + araştırma JSON'ları + dokümandan gecikme. [398](../fbot/api/server.py:398) | Okuma koruması açıksa 401. Bazı alt kaynak hataları 200 içinde `error` olabilir. `run` yokken 1 saniye cache. | `Component.poll()` |
| BE02 | `GET /api/history` | `run`, `limit` (varsayılan 100), `offset` (varsayılan 0) | `run_id, env, run_missing, trades, total, limit, offset, performance, note`. [402](../fbot/api/server.py:402), [history](../fbot/api/history.py:37) | Okuma koruması açıksa 401. Geçersiz sayısal sorgu varsayılana döner. Koşu bulunursa limit 1–500, offset ≥0; bulunamazsa boş yanıt, `run_missing=true` ve `note` yok. | `Component.loadHistory()` |
| BE03 | `GET /api/keys` | Gövde/sorgu gerekmiyor | `status.{testnet,live}`, `services.{testnet,live}`, `note`. Maskeli anahtar durumu; gizli anahtar dönmez. [412](../fbot/api/server.py:412) | Okuma koruması açıksa 401. Servis okuma hatası `services.error` olarak 200 içinde dönebilir. | Anahtar paneli `load()` |
| BE04 | `GET /api/health` | Yok | `ok: true, loading, lines`. [419](../fbot/api/server.py:419) | Okuma koruması açıksa 401. `ok` veri tazeliği veya trader sağlığına bağlı değil; kapsamı sınırlı canlılık yanıtı. | Yok |
| BE05 | `POST /api/kill` | JSON: zorunlu `env`; isteğe bağlı `reason` | `env, path, active` ve kill state alanları. [430](../fbot/api/server.py:430) | 401; bilinmeyen/eksik env için 400 + `envs`. Ortamın kill dosyasını tetikler, state cache'ini geçersizleştirir. | `confirmKill` |
| BE06 | `POST /api/kill/reset` | JSON: zorunlu `env`; isteğe bağlı `note` | `env, path, active` ve reset state alanları. [439](../fbot/api/server.py:439) | 401; bilinmeyen/eksik env için 400. Ortamın kill dosyasını sıfırlar, state cache'ini geçersizleştirir. | `toggleKill` |
| BE07 | `POST /api/keys` | JSON: `env=testnet/live`; isteğe bağlı `key, secret, armed` | `env, updated, file, restart_required, owner_uid, warning, note, status`. [444](../fbot/api/server.py:444), [keys](../fbot/api/keys.py:70) | 401; geçersiz env/değer veya kapalı mainnet kapısı için 400. Anahtar dosyası/izin/sahiplik değiştirir. | Anahtar paneli kaydet/etkinliği kaldır |

Kill ortamları `paper`, `testnet`, `live`; eşleme [envmap.py](../fbot/api/envmap.py:11). Anahtar ortamları yalnızca `testnet`, `live`. `armed` boolean değil, metin; frontend etkinleştirmede UTC tarih metni, kaldırmada boş metin gönderiyor. Boş anahtar girişleri frontend'de gövdeden çıkarılıyor; backend gönderilen alanları güncelliyor. Mainnet için ek `FBOT_LIVE_KEYS_ALLOWED` kapısı var.

## Kimlik doğrulama ve hata sözleşmesi

- POST işlemleri token gerektirir; `FBOT_UI_TOKEN` tanımlı değilse kapalıdır. GET API işlemleri varsayılan olarak açık, `FBOT_UI_PROTECT_READS=1` / `--protect-reads` ile token ister.
- Kabul edilen kimlikler: `X-Fbot-Token`, Bearer veya Basic parolası. Frontend `X-Fbot-Token` kullanıyor. [auth.py](../fbot/api/auth.py:22)
- `_json` yanıtları `application/json; charset=utf-8`, `Content-Length` ve `Cache-Control: no-store` taşır. [server.py](../fbot/api/server.py:380)
- GET yönlendirmesi tam yol karşılaştırması yerine `startswith` kullanır; `/api/state-does-not-exist` de state'e gider. POST yolları tam eşleşir; ek sorgu/trailing slash aynı şekilde normalize edilmez.
- Bilinmeyen POST için JSON 404 vardır; bilinmeyen GET statik dosya sunucusuna düşer, genellikle HTML 404 üretir. Hatalı JSON / JSON nesnesi olmayan POST gövdesi için kontrollü 400 yoktur. Ayrıntı: [EP14–EP15](endpoint-uyum-ve-statik-veri-raporu-2026-09-12.md#ep14--orta--yol-ve-hata-yanıtları-tutarlı-değil).

## `/api/state` alan sözleşmesi

| Alan grubu | Üretilen alanlar | Veri kökeni / anlamı |
|---|---|---|
| Zaman ve tazelik | `t_ms, loading, tail_lines, tail_from_cache, last_event_ns, freshness, stale, stale_flags, staleness_s` | Konsolun izlediği recorder; seçili trader'ın sağlığıyla aynı şey değil |
| Piyasa | `universe[], bars, betas, state_counts, transitions, feed, alarms` | Recorder olaylarından konsolda yeniden hesaplanan görünüm |
| `universe[]` | `sym, price, bid, mark, funding_rate, spread_bps, state, conf, bars, age_bars, warm_pct, features` | Fiyatlar metin/null; spread/conf sayısal/null |
| `bars[symbol][]` | `t, o, h, l, c, v` | Son 72 adet 1 dakikalık OHLCV barı |
| `recorder` | `run_id, restart_no, git_sha, config_hash, start_ns, events, seq, loop_lag_p50, loop_lag_p99, loop_lag_max, queue, dropped, connects, stale_events, snapshots, parse_errors, rate_limit_events` | `frames` alanı **yok** |
| Depolama | `recorder_files[{name,size}], recorder_bytes, disk_free_gb` | Dosya listesi/boyutu ve disk boşluğu; SHA doğrulama sonucu ve toplam disk kapasitesi yok |
| Ortamlar | `mode, kill, kills, environments, paper_running` | `mode` sabit `paper`; gerçek seçili ortam `paper.env`. `kill` eski paper alanı, `kills` ortam haritası |
| Seçili koşu | `paper.{run_id,env,runs,metrics,open_count,gross_exposure_usdt,config_hash,heartbeat,requested_run_id,run_missing}` | Koşu SQLite'ı; eksik `run` isteğinde başka koşuya fallback var |
| Pozisyon/karar | `positions, open_positions, verdicts, fsm, exit_reasons, beta_net_usdt, filters_loaded` | `positions` son 50; açık pozisyonlar ayrı ve limitsiz; kararlar son 25 |
| Ayarlar | `run_config, config.{position,risk,decision,run,source,locked,staleness_s,recorder_run,universe,streams,research}` | İlk üç config bölümü koşudan; recorder/research bölümleri repo TOML'larından; `locked` sabit liste |
| Offline çıktılar | `research, replay_cmp, determinism, latency, phases` | Sabit dosya yollarındaki raporlar; `run` seçimi bunları değiştirmiyor |
| Maliyet | `cost_drift` | DB kapanışlarından, fakat sabit notional/komisyon/funding/slippage varsayımlarıyla yeniden hesaplanıyor |

Kaynaklar: [state birleştirme](../fbot/api/server.py:330), [piyasa snapshot](../fbot/api/live_view.py:133), [koşu snapshot](../fbot/api/paper_view.py:130), [config](../fbot/api/server.py:81).

Pozisyon alanları: `pos_id, symbol, side, state, qty, entry_price, sl, tp, net_pct, exit_reason, opened_ns, closed_ns, entry_state, exit_price, filled_qty`; state görünümü ayrıca `notional_usdt, ref_price` ekliyor. Geçmiş görünümü ayrıca `notional_usdt, net_usdt, hold_ms` ekliyor. Eski DB sütunları eksikse `NULL` seçiliyor.

`history.performance`: `by_symbol, by_exit_reason, by_entry_state, by_side, equity`. Grup alanları `n, wins, net_pct, net_usdt, win_rate, avg_net_pct`. `equity` son 500 kayıtla sınırlı; grup özetleri tüm kapanışları kapsıyor.

`keys.status`: `key_set, secret_set, armed, masked, armed_value, file, hot_reload`; live ayrıca `gate_open`. `keys.services`: `run_id, armed, age_s, reason`; uygulanan anahtar sürümü/fingerprint'i yok.

## Statik HTTP yüzeyi

| Yöntem/yol | Davranış |
|---|---|
| `GET /`, `GET /index.html` | Üretilen konsol HTML'i |
| `GET /support.js`, `GET /vendor/{react.production.min.js,react-dom.production.min.js,babel.min.js}` | Tarayıcı runtime bağımlılıkları |
| `GET /<ui içindeki dosya>` | UI dizini için genel statik servis; kaynak HTML'ler ve `design/` de kod düzeyinde kapsama girer. Proxy üzerinden erişilebilirliği doğrulanmadı. |
| `HEAD /<yol>` | Üst sınıftan miras statik HEAD. Özel API JSON işleyicisine gitmez; API GET işlemleri için eşdeğer HEAD sözleşmesi yok. |

Özel PUT/PATCH/DELETE/OPTIONS işleyicisi, WebSocket veya SSE sunucu endpoint'i tespit edilmedi. Desteklenmeyen yöntemler stdlib davranışına bırakılıyor.

## Doğrulama

- Python AST ile GET/POST yol sabitleri çıkarıldı; 7 işlem bulundu.
- Yedi işlem gerçek handler metotlarıyla **bellekte**, yazıcılar ve veri kaynakları mock edilerek çağrıldı; tamamı beklenen 200 dalına ulaştı. State/history sorgu parametrelerinin aktarımı doğrulandı. Bu, DB işlemlerinin ve gerçek POST yan etkilerinin uçtan uca doğrulaması değildir.
- Çalışan `/api/state` JSON'u 2026-09-12 **11:33:43.064 UTC** anında okundu: `paper.env=paper`, `freshness.status=live`, veri yaşı `0.2 s`; `recorder.frames` yok, `config.decision.max_state_age_bars=3`.
- Diğer GET endpoint'leri çalışan servis üzerinde çağrılmadı. Gerçek POST gönderilmedi; servis başlatılmadı/yeniden başlatılmadı.

İlişkili belgeler: [frontend envanteri](frontend-endpoint-envanteri-2026-09-12.md), [uyum ve statik veri raporu](endpoint-uyum-ve-statik-veri-raporu-2026-09-12.md), [TODO](../TODO.md).
