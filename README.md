# fbot

Binance USDⓈ-M Futures üzerinde deterministik, event-driven işlem sistemi. Durum: **Faz 1** (ham veri kaydı). Ayrıntı: `CLAUDE.md`, `docs/PHASE.md`, `docs/decisions/`.

## Kurulum

```bash
make setup          # venv + websockets + pytest
make test           # 87 test
make test-determinism   # Rule Zero: iki process, aynı hash
```

Docker (Ubuntu deposu): `docker.io`, `docker-compose-v2`.

## Faz 1 — recorder

TOP 10 sembol (24 s hacim, stablecoin çiftleri hariç), `/public` ve `/market` kategorileri ayrı bağlantıda, tek sıralama noktası, saatlik gzip rotasyon, manifest ile SHA-256.

```bash
make run-recorder REC=deneme DURATION=60     # yerel, 60 s
make verify-recording REC=deneme             # bütünlük raporu (Markdown)
make verify-orderbook REC=deneme MAXF=2      # local order book replay doğrulaması

make docker-build
make up REC=rec-72h                          # arka planda, restart: unless-stopped
make logs
make down
```

Kayıt: `data/recordings/<run_id>/events-<UTC saat>-<ilk seq>.jsonl.gz`, `manifest.jsonl`, `runs.jsonl`.
Satır formatı: `{"q":seq,"r":recv_ns,"m":mono_ns,"c":cat,"s":stream,"d":<ham çerçeve>}` (ADR 0005).

Config: `config/recorder.toml`. Bayatlık eşikleri başlangıç değeridir; 72 saatlik kayıttan sonra ölçümle güncellenir.

## Faz 2 — deterministik çekirdek ve replay

`fbot/core/engine.py`: `step(state, event, now_ns) -> (state, commands)`; saf, `Decimal`. Komutlar: `BarClosed` (1 dk, işlem zamanı `T` ile), `StalenessChanged`. Replay hash'i `sha256(seq|canonical(cmd))` zinciri.

```bash
make replay REC=rec-72h MAXF=1      # gerçek kayıt; hash, komut sayısı, olay/s
```

Maliyet modeli `fbot/costs.py` (komisyon, funding, slippage; oranlar `CostConfig`). Execution: `fbot/execution/adapter.py`, Live adapter korumalı stub.

## Faz 3 — offline araştırma (DUR kapısı)

```bash
make export-bars REC=rec-72h        # replay → data/research/rec-72h/bars.jsonl
make research-report REC=rec-72h    # → docs/research/rapor-rec-72h.md (deterministik, seed'li)
```

Metodoloji ADR 0008; hipotezler `docs/research/hipotezler.md`; config `config/research.toml`.

## Konsol (fbot Console)

Tasarım: claude.ai/design projesi "Binance Trading Bot Interface" (`ui/design/` kaynak). `ui/index.html` = tasarım şablonu + `/api/state`'e bağlı veri sınıfı (`ui/console-logic.html`). React/Babel `ui/vendor/` altında (SRI doğrulandı), dış CDN yok.

```bash
make ui REC=rec-72h     # API + statik servis, 127.0.0.1:8787; kayıt dosyasını canlı tail eder
make ui-stop
```

API: `GET /api/state` (çekirdekle türetilen canlı piyasa görünümü, recorder istatistikleri, fazlar, araştırma ve replay JSON'ları, config, kill switch), `POST /api/kill`, `POST /api/kill/reset`. Yalnızca yerel bağlama; uzaktan erişim SSH tüneli ile. Pozisyon ve risk ekranları paper trading (Faz 7) başlayana kadar boş.

## Faz 0 — ölçüm

```bash
make measure-latency RUN=<id>     # 24 saat, 4 process
make summarize-latency RUN=<id>
make unit-economics
```

## Güvenlik

API anahtarı yok (Faz 1'de gerekmiyor). `.env` gitignore'da; yalnızca `.env.example` repoda.
