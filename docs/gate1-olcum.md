# Gate 1 ölçümü — veri yolu ve kimlik

Tarih: 2026-09-12 · Commit: `b8abed83373e` (+ `a2dcd01948ba` heartbeat eki) · ADR 0017

Ölçüm betiği: `make trader-load F=<dosya>` (`scripts/trader_load.py`). Her sayı gerçek bir koşu
dosyasından okunmuştur; varsayımla belirlenen değer yoktur.

## 1. Çıkış koşulu: hash-nötrlük

| Kapı | Sonuç |
|---|---|
| `make test-determinism` (saflık + iki process bit-eşitliği + golden hash) | **yeşil** |
| `make golden` (sabitlenmiş komut hash'i, komut sayısı, `by_kind`) | **yeşil, değişmedi** |
| `make test` | 472 → **495 geçti** |
| `make bench-guard` | yeşil |

Saf çekirdekte tek değişiklik `CoreState`'teki yinelenen alan tanımları ile `_risk_inputs`'taki
yinelenen bloğun silinmesidir. Golden hash bunun davranışsız olduğunu kanıtlıyor.

## 2. `Engine.step` (değişmemeli)

Aynı fixture, üç koşu, tek çekirdek:

| | p50 µs | p99 µs |
|---|---|---|
| Gate 1 öncesi (`154fb45`) | 6,92 · 7,04 · 6,92 | 19,5 · 30,2 · 24,9 |
| Gate 1 sonrası | 7,03 · 7,32 · 7,13 | 18,6 · 22,4 · 17,4 |

Fark gürültü içinde; p99'un koşudan koşuya oynaması (17–30 µs) ölçümün kendi dağılımıdır.
Sabitlenmiş baseline p50 6,9 / p99 15,1 µs; regresyon kapısı (p99 > baseline × 1,5) geçiyor.

## 3. Hot path'te SQLite

| Ölçüt | Öncesi | Sonrası |
|---|---|---|
| Olay işleme yolunda çalışan SQL ifadesi | pozisyon başına 1 `INSERT` (her olayda) | **0** |

Kanıt: `tests/test_persistence_writer.py::test_hot_path_does_no_sqlite_work_at_all` bağlantıya
`set_trace_callback` takıp 200 kayıt isteği üretiyor; yazıcı görevi çalışmadan önce sayaç sıfır.

**Dürüst sınır:** canlı `fbot-paper` koşusunda `allowed_cells` boş olduğu için bugün hiç pozisyon
ve karar satırı üretilmiyor (`persist.written = 0`). Yani asenkron kalıcılığın canlı yük altındaki
kazancı **bugün ölçülemez**; strateji açıldığında ölçülecektir. Bugün kanıtlanan şey yapının
kendisidir: kuyruk, `to_thread` yazımı, drop sayacı ve kapanışta boşaltma.

## 4. Stream profilleri — trader yükü

Karşılaştırma tek değişkenli: aynı sembol evreni, aynı saat dilimi, yalnız profil değişti.

Pencereler: **öncesi** 07:00–08:00 UTC (tam saat, eski imaj), **sonrası** 08:23–08:43 UTC
(yeni imaj, 19,6 dk). Piyasa etkinliği iki pencerede aynı değildir; bu yüzden toplam olay/s
değil **stream başına oran** karşılaştırılır.

### `fbot-testnet` (profil `trader_testnet`)

| stream | öncesi /s | sonrası /s |
|---|---|---|
| bookTicker | 254,76 | 313,80 |
| depth@100ms | 19,58 | **0,00** |
| aggTrade | 7,86 | 10,05 |
| markPrice@1s | 2,00 | 1,99 |
| toplam | 285,20 | 326,83 |

`depth@100ms` tamamen kalktı. bookTicker ve aggTrade oranı %23 arttı — bu piyasa etkinliğidir,
değişikliğin sonucu değil. Yani testnet süreci **daha yoğun bir piyasada daha az CPU harcıyor**:

| | öncesi | sonrası |
|---|---|---|
| CPU | %7,44 (tek örnek, 12 saat uptime) | ort **%4,74**, medyan %3,25, 18 örnek |
| RSS | 201 MiB (12 saat uptime) | 32,4 MiB (20 dk uptime) |

RSS karşılaştırması eşit uptime'da değil. Eşit uptime karşılaştırması şudur: aynı anda başlatılan
iki süreçten 20 dakika sonra **paper 194 MiB, testnet 32 MiB**. Aradaki fark L2 defterleridir;
testnet artık kurmuyor.

### `fbot-paper` (profil `trader_paper`)

| stream | öncesi /s | sonrası /s |
|---|---|---|
| bookTicker | 683,74 | 725,53 |
| depth@100ms | 90,66 | 89,63 |
| aggTrade | 58,06 | 57,99 |
| markPrice@1s | 10,00 | 9,99 |
| forceOrder | 0,02 | **0,00** |

Paper'da tek değişiklik `forceOrder`'ın kalkmasıdır: saniyede 0,02 olay, yani **ölçülebilir bir
kazanç yok**. Beklenen de buydu; paper depth'e ihtiyaç duyuyor (dolum simülatörü).

| | öncesi | sonrası |
|---|---|---|
| CPU | %14,16 (tek örnek) | ort %12,22, medyan %11,37, 18 örnek |
| loop lag p50 (medyan) | 0,58 ms | 0,58 ms |
| loop lag p99 (medyan) | 1,87 ms | 1,89 ms |
| loop lag en kötü p99 | 249,81 ms | 164,76 ms |

Paper CPU farkı tek örnekle 18 örneğin ortalaması arasındadır; **anlamlı bir düşüş iddiası için
yeterli değildir**, yalnızca regresyon olmadığını gösterir.

## 5. Kalıcılık kuyruğu

| Ölçüt | paper | testnet |
|---|---|---|
| `queued` / `depth_p99` / `depth_max` | 0 / 0 / 0 | 0 / 0 / 0 |
| `written` | 0 | 0 |
| `dropped` | 0 | 0 |
| `errors` | 0 | 0 |

Kuyruk boş çünkü `allowed_cells` boş: bugün ne karar ne pozisyon satırı üretiliyor (bu değerler
Gate 1 öncesinde de sıfırdı, veri kaybı yok). Kuyruk derinliği ve drop sayacı konsola
`paper_stats.persist` ve canlılık damgası üzerinden yayılıyor; strateji açıldığında ölçülecek
yer burasıdır.

## 6. Loop lag — açık kalan bulgu (Gate 1 kapsamı dışı)

`fbot-testnet`'te loop lag en kötü p99 **3.252 ms → 3.214 ms**; yani **değişmedi**. Bu diken
kalıcılıktan gelmiyor: senkron REST çağrıları (silahlanma denetimi, mutabakat, emir yolu) döngüyü
tutuyor. Düzeltmesi Gate 2.1 (bloklamayan transport) kapsamındadır.

## 7. Şema göçü — canlı doğrulama

`data/recordings/paper/paper.db` ve `data/recordings/testnet/paper.db` yeni imajla açıldığında
göç etti: `runs` tablosu oluştu, satır tablolarına beş kimlik sütunu eklendi, satır sayıları
değişmedi (ikisi de zaten boştu). Konsol (`fbot-console`) göçten sonra `/api/state` ve
`/api/health` isteklerine normal yanıt veriyor.

Yeniden başlatma kimlikleri: paper `restart_no=2`, testnet `restart_no=8`,
`code_hash=8415aed628ee`, `git_sha=b8abed83373e` / `a2dcd01948ba`.

## BU ÖLÇÜMDE YAPILMAYANLAR

- **Asenkron kalıcılığın canlı yük altındaki kazancı ölçülmedi.** Strateji kapalı olduğu için
  yazılacak satır yok. Yapının doğruluğu testle, kazancı değil.
- **Paper tarafında stream profilinin kazancı ölçülemedi** (yalnız `forceOrder` kalktı, 0,02 ev/s).
- **Öncesi CPU değerleri tek örnektir**, sonrası 18 örneğin ortalamasıdır. Paper için fark
  anlamlılık iddiası taşımaz.
- **RSS öncesi/sonrası eşit uptime'da değildir.** Eşit uptime kıyası yalnız paper–testnet arasında
  yapıldı (194 MiB / 32 MiB).
- `fbot-recorder`'a dokunulmadı; ölçümü yalnız kontrol amaçlı alındı (ort %9,34 CPU, 240 MiB).
