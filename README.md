# fbot

Binance USDⓈ-M Futures üzerinde deterministik, event-driven işlem sistemi. Durum: **Faz 1** (ham veri kaydı). Ayrıntı: `CLAUDE.md`, `docs/PHASE.md`, `docs/decisions/`.

## Kurulum

```bash
make setup          # venv + websockets + pytest
make test           # 46 test
```

Docker (Ubuntu deposu): `docker.io`, `docker-compose-v2`.

## Faz 1 — recorder

TOP 10 sembol (24 s hacim, stablecoin çiftleri hariç), `/public` ve `/market` kategorileri ayrı bağlantıda, tek sıralama noktası, saatlik gzip rotasyon, manifest ile SHA-256.

```bash
make run-recorder REC=deneme DURATION=60     # yerel, 60 s
make verify-recording REC=deneme             # bütünlük raporu (Markdown)

make docker-build
make up REC=rec-72h                          # arka planda, restart: unless-stopped
make logs
make down
```

Kayıt: `data/recordings/<run_id>/events-<UTC saat>-<ilk seq>.jsonl.gz`, `manifest.jsonl`, `runs.jsonl`.
Satır formatı: `{"q":seq,"r":recv_ns,"m":mono_ns,"c":cat,"s":stream,"d":<ham çerçeve>}` (ADR 0005).

Config: `config/recorder.toml`. Bayatlık eşikleri başlangıç değeridir; 72 saatlik kayıttan sonra ölçümle güncellenir.

## Faz 0 — ölçüm

```bash
make measure-latency RUN=<id>     # 24 saat, 4 process
make summarize-latency RUN=<id>
make unit-economics
```

## Güvenlik

API anahtarı yok (Faz 1'de gerekmiyor). `.env` gitignore'da; yalnızca `.env.example` repoda.
