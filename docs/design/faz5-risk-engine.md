# Faz 5 tasarım notu — Risk Engine

Tarih: 2026-09-10 · Durum: tasarım notu, kod yok. Faz 5, Faz 4 kapısından sonra başlar; sayısal eşiklerin hiçbiri burada sabitlenmez.

## 1. Konum ve yetki

- Decision Engine'den **bağımsız**, **veto** yetkili. Çıktı: `APPROVE | REJECT | RESIZE`.
- Saf çekirdekte yaşar: `assess(intent, state, cfg, now_ns) -> Verdict(kind, reasons, qty)`; I/O yok, tüm girdiler state'ten. Gerekçe listesi deterministik sırada (aşağıdaki katalog sırası) → replay'de bit-eşit.
- **Fail-closed:** herhangi bir girdi eksik, bayat ya da güvenilmezse yeni pozisyon açılmaz. Şüphe = REJECT.
- **Çıkışları asla engellemez.** `reduceOnly` / `closePosition` komutları yalnızca filtre ve emir bütçesi kontrolünden geçer; kill switch, bayatlık, maruziyet, cooldown çıkışa uygulanmaz. Fail-safe = kapatmak.

## 2. Girdi gerçekleri

| Girdi | Kaynak | Not |
|---|---|---|
| Pozisyon, bakiye, teminat | user data stream (`ACCOUNT_UPDATE`), açılışta REST mutabakatı | volatil piyasada REST gecikir (doğrulandı) |
| Emir sayaçları | `X-MBX-ORDER-COUNT-10S/1M` header'ları ve WS `rateLimits` alanı (ORDERS per-UID, REST ile paylaşımlı) | tahmini sayaç yetmez; gerçek değer |
| Sembol filtreleri | `exchangeInfo` (tick, step, minQty, MIN_NOTIONAL, PERCENT_PRICE, MARKET_LOT_SIZE) | BTC gerçek minimum 78 USDT ölçüldü |
| Bayatlık | `StalenessChanged` (Faz 2) | kategori bazlı |
| Clock skew | Faz 0 ölçümü: p99 191 ms, maks 486 ms (1 saat) | `recvWindow` 5000 |
| Durum ve feature'lar | Faz 3 (`W`, `2W` ısınma) | ısınma süresi buradan |
| Maliyet | Faz 2 `costs.py`, ölçülen spread | maliyet sürüklenmesi metrikleri |

## 3. Kontrol kataloğu (sıra = değerlendirme ve gerekçe sırası)

| # | Kontrol | Kural | Sonuç | Parametre (config, başlangıçta `null`) |
|---|---|---|---|---|
| K1 | Kill switch | kalıcı bayrak açık | REJECT | — |
| K2 | Mutabakat | açılış mutabakatı tamamlanmadı ya da uyuşmazlık | REJECT | — |
| K3 | Isınma | sembolün feature pencereleri dolu değil (`2W` bar) | REJECT | `W` (Faz 3) |
| K4 | Bayatlık | ilgili kategori bayat (public **veya** market) | REJECT | `staleness_ms` (24 s ölçümden) |
| K5 | Clock skew | `abs(skew) > skew_max` | REJECT | `skew_max` (< recvWindow/2 önerisi) |
| K6 | Eşzamanlı pozisyon | açık + bekleyen giriş ≥ 5 | REJECT | 5 (kilitli) |
| K7 | Sembol maruziyeti | sembolde açık pozisyon var (one-way) ya da bekleyen giriş var | REJECT | — |
| K8 | Toplam maruziyet | Σ notional + yeni > `gross_cap` | RESIZE → sığmıyorsa REJECT | `gross_cap` |
| K9 | BTC-beta net maruziyet | `abs(Σ yön×notional×beta_s + yeni)` > `beta_cap` | RESIZE / REJECT | `beta_cap`, `beta_window` |
| K10 | Kaldıraç | sembol kaldıracı config'le (BTC/ETH 10x, diğer 5x) ve borsadaki ayarla eşleşmiyor | REJECT | kilitli |
| K11 | Teminat | `availableBalance` < gerekli teminat × (1 + `margin_buffer`) | REJECT | `margin_buffer` |
| K12 | Filtreler | miktar step'e **aşağı** yuvarlanır; `minQty`/`MIN_NOTIONAL`/`MARKET_LOT_SIZE.maxQty`/`PERCENT_PRICE` ihlali | REJECT (yukarı yuvarlama yok) | exchangeInfo |
| K13 | Spread | spread_bps > `spread_max` | REJECT | `spread_max` (sembol başına persentil) |
| K14 | Likidite / katılım | notional / (defterde ±`depth_bps` içindeki notional) > `participation_max` | RESIZE / REJECT | `depth_bps`, `participation_max` |
| K15 | Slippage tahmini | defter yürüyüşü > `slippage_max_bps` | REJECT | `slippage_max_bps` |
| K16 | Cooldown | son çıkıştan bu yana < `cooldown_ms` (zararlı çıkışta `cooldown_loss_ms`), ya da son STP `EXPIRED_IN_MATCH` sonrası < `cooldown_stp_ms` | REJECT | üç süre |
| K17 | Emir bütçesi | 10 s / 1 dk sayaçlarında kalan < `reserve_orders` (koruma emirleri için ayrılmış) | REJECT | `reserve_orders` (≥ SL+TP+iptal = 3 önerisi) |
| K18 | 429/418 durumu | son 429'dan sonra `backoff_ms` geçmedi; 418 → kill switch | REJECT | `backoff_ms` |

Kontroller yalnızca **giriş** niyetlerine tam uygulanır. K12 ve K17 çıkışlara da uygulanır; K17 çıkışta reddetmez, yalnızca alarm üretir (bütçe koruma emirleri için zaten ayrılmıştır).

## 4. Kalıcı kill switch

- Depolama: `data/state/kill_switch.json` (`{active, reason, ts_ns, git_sha, trigger}`); restart'ta okunur; açıksa K1 her girişi reddeder; **çıkışlar serbest**.
- Tetikleyiciler: HTTP 418; mutabakat uyuşmazlığı; runaway (aşağıda); günlük net zarar limiti (**proje sahibi kararı gerekli**, §8); koruma ACK'i gelmeyen pozisyon sayısı ≥ 1; elle (`make kill`).
- Sıfırlama yalnızca elle: `make kill-reset REASON="..."`; sıfırlama olayı kayda yazılır. Otomatik açılma yok.
- Runaway dedektörü (Faz 0 itirazı): kayan pencerede gönderilen emir sayısı > `runaway_orders_per_min` ya da aynı sembolde ardışık ret sayısı > `runaway_rejects` → kill switch. Bu günlük işlem limiti değildir; arıza dedektörüdür.

## 5. Açılış mutabakatı

1. REST: pozisyonlar, açık emirler, açık algo emirleri, bakiye, kaldıraç ayarları, `exchangeInfo`.
2. İç state (son kayıt/persist) ile karşılaştırma: sembol, yön, miktar, koruma emirlerinin varlığı ve `clientAlgoId` şeması.
3. Uyuşmazlık → `RECONCILE_LOCKED`: giriş yok; açık pozisyonlar FROZEN (Faz 4); korumasız pozisyon varsa **derhal** SL+TP yerleştirilir (koruma her zaman önce), sonra proje sahibine alarm.
4. Mutabakat başarılı → user data stream'e geçiş; REST yalnızca periyodik (`reconcile_interval`) mutabakat.

## 6. BTC-beta maruziyeti

- `beta_s` = sembolün 1 dk log getirisinin BTCUSDT'ye rolling regresyon eğimi (`beta_window` bar; Faz 3 bar serisinden). BTC için 1.
- Net beta maruziyeti = Σ (yön × notional × beta_s). 5 altcoin long ≈ tek büyük BTC long; K9 bunu sınırlar.
- `beta_cap` başlangıçta bilinmiyor; ilk tahmin: 3 günlük kayıttan sembol betalarının dağılımı raporlanır, sonra proje sahibi karar verir.

## 7. Maliyet sürüklenmesi (alarm, veto değil — prompt 6.4)

Kayan dönemde (`drift_window`): komisyon / brüt kâr; toplam maliyet (komisyon + funding + slippage) / sermaye; işlem başına ortalama net. Eşik aşımında **alarm** (metrik + log), işlem engellenmez. Eşikler config.

## 8. Proje sahibine sorular (Faz 5 başında)

1. Günlük net zarar limiti kill switch tetikleyicisi olsun mu? Değeri (teminatın yüzdesi) sen verirsin.
2. `gross_cap` ve `beta_cap`: 80 USDT × 5 pozisyon = 400 USDT brüt tavan makul mü, yoksa daha düşük mü?
3. Zararlı çıkış sonrası cooldown istiyor musun? (Sezgi: evet; ölçüm yok.)

## 9. Kabul kriterleri (taslak)

1. K1–K18 saf, her biri birim testli; gerekçe sırası deterministik.
2. Hata enjeksiyonu (BÖLÜM 11 eşlemesi): WS kopması → K4; mutabakat uyuşmazlığı → K2 + FROZEN; 429 → K18 geri çekilme; 418 → kill; emir cevabı kaybı → mutabakat sonrası idempotent yeniden deneme; sembol filtresi ihlali → K12; Risk Engine girdisi eksik → REJECT; runaway → kill.
3. Kill switch restart'ı hayatta kalır (test: bayrak yaz, process yeniden başlat, giriş reddedilir).
4. Çıkış komutları hiçbir K1–K16 tarafından engellenmez (test).
5. Replay determinizmi korunur.

## 10. Bu notta olmayanlar

- Eşik değerleri; hepsi ölçüm ya da proje sahibi kararı.
- Persist katmanı (DB) seçimi — Faz 5 ADR'si.
- Canlı emir yolu ve API anahtarı gerektiren mutabakat testi (Faz 9).
