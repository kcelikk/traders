# ADR 0017 — Koşu kimliği, asenkron kalıcılık ve rol bazlı stream profilleri (Gate 1)

Tarih: 2026-09-12 · Durum: kabul edildi · Kapsam: Gate 1 (hash-nötr)

## Bağlam

Mimari incelemesi (`docs/mimari-inceleme-2026-09-11.md`) ve Gate 0 taraması üç yapısal boşluk çıkardı:

1. **Atıf yok.** `paper.db` satırları yalnızca `run_id` ve ham config hash'i taşıyordu. Hangi
   satırın hangi modda (paper/testnet), hangi kod sürümüyle ve hangi strateji sürümüyle üretildiği
   sonradan türetilemiyordu. Container'da `git_sha` "unknown" dönebiliyor
   (`fbot/recorder/main.py`), yani kod sürümünü söyleyecek başka bir şey de yoktu.
2. **SQLite hot path'te.** `PaperTrader._record_positions` her olayda, her açık pozisyon için
   `Decimal→str` dönüşümü + `INSERT` yapıyordu. Paper koşusunda ölçülen yük 844 olay/s.
3. **Kullanılmayan veri.** Testnet süreci `_NullSim` kullanmasına rağmen `depth@100ms` akışına
   abone oluyor ve tam L2 defterini kuruyordu; bu veriyi hiç tüketmiyor. Her iki trader da
   `forceOrder` alıyordu; çekirdek bunu tüketmiyor (H9/H10 reddedildi).

Şema iki kez değiştirilmemelidir: yalnız async yazıma geçip sonra sütun eklemek, yazıcı görevinin
eski şemayla dolmuş kuyruğu yeni şemaya yazmasına yol açar. Bu yüzden kimlik alanları ile
asenkron kalıcılık **aynı anda** yapılır.

## Seçenekler

**Kimlik için:** (a) yalnız `run_id`, gerisi dosya adından çıkarılsın — kırılgan, yeniden
başlatmada çöker. (b) ayrı bir `runs` tablosu + satır bazında alt küme — seçildi. (c) her satıra
tüm kimlik — yer israfı, değişmez alanlar tekrarlanır.

**Kalıcılık için:** (a) senkron kalsın, `flush` aralığı büyütülsün — `INSERT` yine döngüde.
(b) sınırlı kuyruk + yazıcı görevi + `asyncio.to_thread` — seçildi. (c) ayrı süreç (PROCESS 3) —
doğru uzun vadeli hedef ama bugün gereksiz karmaşa; kuyruk arayüzü onu engellemiyor.

**Stream için:** (a) sembol bazlı azaltma — evren zaten 10 sembol, kazanç yok. (b) rol bazlı
profil — seçildi. (c) trader'ların recorder kaydını okuması — süreçler arası hop, hot path'e ağ
eklenemez (CLAUDE.md yasağı).

## Karar

### 1. `RunIdentity` (`fbot/identity.py`)

`run_id, mode, strategy_id, strategy_version, config_hash, config_semantic_hash, code_hash,
reactor_id, git_sha, restart_no`. `core/` altında değildir çünkü dosya okur.

- `code_hash` = `fbot/**/*.py` içeriklerinin sıralı sha256'sı (12 hex). `git_sha` "unknown"
  olduğunda kodun kimliğini veren tek alan budur.
- İki config hash'i birlikte tutulur: ham bayt hash'i (`fbot/config.py`) yorum değişince de
  değişir ve ortam değişkeni override'larını görmez; `config_semantic_hash`
  (`fbot/paper/config_view.py`) etkin değerlerin kanonik JSON'unun hash'idir.
- `reactor_id` bugün `None`. Gate 4'te doldurulacak; sütunu şimdi açıyoruz ki şemaya ikinci kez
  dokunulmasın.

### 2. `runs` tablosu doğruluk kaynağıdır

Her başlatma `(run_id, restart_no)` anahtarıyla bir satır yazar. `meta.env` kilidi kalktı: eskiden
veritabanındaki değer çağıranı eziyordu, artık kimliği veren çağıran kazanır. Satır bazlı
tablolara (`decisions`, `orders`, `fills`, `positions`) beş sütun eklendi:
`mode, strategy_id, strategy_version, code_hash, reactor_id`. Göç yalnız `ADD COLUMN`; eski
satırlar `NULL` kalır — "bilinmiyor" doğru cevaptır, uydurma değil.

Okuma sorguları (`summary`, `recent_positions`, `recent_decisions`) artık `WHERE run_id=?`
taşıyor; aynı dosyada iki koşu varsa özet karışmıyordu, sessizce toplanıyordu.

### 3. `AsyncStore` (`fbot/persistence/writer.py`)

Sınırlı `asyncio.Queue` + yazıcı görevi. Görev kuyruğu toplu boşaltır ve `asyncio.to_thread` ile
uygular; SQLite hiçbir zaman döngüyü tutmaz. `PaperStore` bağlantısı kilitle korunur (yazım ayrı
thread'te, heartbeat/okuma döngü thread'inde).

Kuyruk dolarsa satır **düşürülür ve sayılır**; sessiz kayıp yok. Düşen satır görünüm/rapor
verisidir: kararlar bellekte, ham akış recorder dosyasındadır. Kapanışta `queue.join()` ile
boşaltılır.

`PaperTrader._record_positions` kirli-bayrak kullanır: durumu değişmemiş pozisyon her olayda
yeniden yazılmaz, tick'te (1 s) tazelenir. `net_pct` mark fiyatından türediği için tazeleme tick'e
bağlıdır; bu yol yalnız kayıttır, karara girmez.

### 4. Rol bazlı stream profilleri (`[streams] profile`)

| profil | stream'ler | kim |
|---|---|---|
| `recorder` | bookTicker, depth, aggTrade, markPrice, forceOrder | `fbot-recorder` — araştırma girdisi eksiksiz kalır |
| `trader_paper` | bookTicker, depth, aggTrade, markPrice | `fbot-paper` — depth dolum simülatörünün girdisi (ADR 0013) |
| `trader_testnet` | bookTicker, aggTrade, markPrice | `fbot-testnet` — simülatör yok, depth tüketilmiyor |

Bilinmeyen profil veya bilinmeyen stream şablonu `ConfigError`. Fail-closed: profil `depth`
içermiyor ve `sim.book_levels > 0` ise `PaperConfigError` — aksi hâlde dolum simülasyonu sessizce
bozulurdu.

## Sonuçlar

- Gate 1 hash-nötrdür: `make test-determinism` ve golden baseline yeşil kaldı. Saf çekirdekte tek
  değişiklik `CoreState`'teki yinelenen alan tanımlarının ve `_risk_inputs`'taki yinelenen bloğun
  silinmesidir (aynı değeri iki kez yazıyorlardı; golden bunu kanıtlıyor).
- Ölçüm sonuçları `docs/gate1-olcum.md`.
- `strategy_id`/`strategy_version` bugün `[run]` bölümünden okunur ve boştur. Gate 5 strateji
  kaydını bağlayınca dolacak.
- PROCESS 3 (ayrı kalıcılık süreci) ertelendi; kuyruk arayüzü onu engellemiyor.
