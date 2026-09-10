# ADR 0005 — Faz 1: gateway + recorder aynı process, kayıt formatı

Tarih: 2026-09-10 · Durum: kabul edildi (Faz 1 başlangıcı)

## Bağlam

Rule Zero: replay girdisi, çekirdeğin gördüğü sıralı akışın kendisi olmalı. Prompt 5.1'de recorder bus'ın öbür tarafında; bus fire-and-forget olduğu için kayıt akışı çekirdek akışından sapabilir (Faz 0 itirazı). Faz 1'de çekirdek yok; yalnızca gateway + kayıt var.

## Karar

1. **Tek sıralama noktası gateway'dir ve kaydı gateway'in process'i yazar.** Her kategori bağlantısından gelen ham çerçeve, aynı asyncio döngüsünde `Sequencer.next()` ile monoton `seq` alır ve bir `asyncio.Queue` üzerinden aynı thread'deki writer görevine gider (write-behind). Hot path'te senkron disk I/O yok; ağ hop'u yok.
2. **Ham çerçeve bayt-bayt saklanır**, yeniden serileştirilmez. Kayıt satırı: `{"q":seq,"r":recv_ns,"m":mono_ns,"c":cat,"s":stream,"d":<ham çerçeve>}`. `recv_ns` duvar saati (ns), `mono_ns` monotonik (ns). Kontrol olayları (`connect`, `disconnect`, `stale`, `snapshot`, `stats`, `run_start`, `run_end`) aynı sıralı akışta `c="ctrl"` ile yer alır; replay bunları da görür.
3. **Dosya:** saatlik rotasyon, gzip, `events-<UTC saat>-<ilk seq>.jsonl.gz`. Her dosya kapanışında `manifest.jsonl`'e satır: dosya adı, ilk/son seq, satır sayısı, sıkıştırılmamış SHA-256, byte sayısı. Run başında `run.json`: run id, git SHA, config hash, sembol listesi, stream listesi, başlangıç zamanı.
4. **Depth snapshot'ları kayıtta.** Bağlantı kurulunca ve her `snapshot_interval_s` saniyede `GET /fapi/v1/depth limit=1000` (ağırlık 20) çekilir ve `ctrl/snapshot` olayı olarak akışa yazılır; replay local order book'u dokümandaki kurala göre kurar.
5. **Kayıt kapsamı (Faz 1):** `/public`: `@bookTicker`, `@depth@100ms`; `/market`: `@aggTrade`, `@markPrice@1s`, `@forceOrder`. Kline kaydedilmez (aggTrade'den deterministik türetilir). Private stream Faz 1'de yok (anahtar gerektirir).
6. **Config:** TOML, stdlib `tomllib`; yeni bağımlılık yok. Config hash = dosya içeriğinin SHA-256 ilk 12 hex'i.
7. **Docker:** `python:3.12-slim`, root olmayan kullanıcı, `data/` volume, `restart: unless-stopped`. Sistem paketleri: `docker.io 29.1.3`, `docker-compose-v2 2.40.3` (Ubuntu deposu; dış apt deposu eklenmedi).

## Seçenekler ve red gerekçeleri

- Recorder'ı bus üzerinden beslemek: kayıp riski, Rule Zero ihlali. Reddedildi.
- Parquet/Arrow: bağımlılık ekler, ham baytı korumaz. Faz 3 araştırması için dönüştürücü yazılabilir; kaynak format değişmez.
- Ayrı thread'de gzip: determinizmi etkilemez (yalnızca I/O kenarı) ama GIL nedeniyle kazanç belirsiz; önce ölçülür (loop lag metriği). Gerekirse ayrı process.

## Sonuçlar

- Loop lag, kuyruk derinliği ve mesaj sayaçları her 10 s'de `ctrl/stats` olayı olarak akışa yazılır; gate raporu bunlardan üretilir.
- Faz 2 replay, aynı satır formatını okur; `recv_ns` replay saatidir.
- Bilinmeyen: 10 sembol × 5 stream'in 72 saatlik disk hacmi. Ölçülecek.
