# fbot — tekrar edilebilir komutlar. Var olmayan hedef yazılmaz.
PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
RUN ?= baseline-24h-20260910
REC ?= rec-72h
GIT_SHA := $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)

.PHONY: setup status ui ui-stop test test-determinism replay replay-positions export-bars research-report research-scan fetch-history build-history-bars measure-latency summarize-latency unit-economics run-recorder verify-recording verify-orderbook docker-build up down logs

setup:
	python3 -m venv .venv
	$(PIP) install -q -r requirements-dev.txt
	$(PY) -c "import websockets, pytest; print('ok', websockets.__version__, pytest.__version__)"

status:                  # arka plan süreçleri ve veri durumu
	@date -u '+%Y-%m-%dT%H:%MZ'
	@docker inspect -f 'recorder: {{.State.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}' fbot-recorder 2>/dev/null || echo "recorder: yok"
	@du -sh data/recordings/$(REC) 2>/dev/null | awk '{print "kayıt:", $$1}'; ls data/recordings/$(REC)/*.gz 2>/dev/null | wc -l | awk '{print "kayıt dosyası:", $$1}'
	@echo "gecikme ölçümü process: $$(pgrep -cf '[m]easure_latency --duration')"; wc -l < data/latency/$(RUN)/rest_keepalive.jsonl 2>/dev/null | awk '{print "REST örnek:", $$1, "(24 s ≈ 43200)"}'
	@echo "sonraki: 2026-09-11 07:39Z gecikme nihai raporu; 08:00Z sonrası 24 s araştırma ön raporu; 2026-09-13 08:00Z sonrası nihai/DUR"

ui:                      # konsol: http://127.0.0.1:8787 (SSH tüneli: ssh -L 8787:127.0.0.1:8787 <sunucu>)
	@nohup $(PY) -m fbot.api.server --run-dir data/recordings/$(REC) --history-files $(or $(HIST_FILES),5) > data/ui.log 2>&1 & echo $$! > data/ui.pid
	@sleep 2; curl -s http://127.0.0.1:8787/api/health; echo

ui-stop:                 # pidfile ile (pkill -f pattern'i kendi shell'ini de öldürebiliyor)
	@if [ -f data/ui.pid ]; then kill $$(cat data/ui.pid) 2>/dev/null; rm -f data/ui.pid; echo "durduruldu"; else echo "pidfile yok"; fi

test:
	$(PYTEST) -q tests

test-determinism:        # Rule Zero: fixture iki ayrı process'te, hash eşit; mutasyonda farklı
	$(PYTEST) -q tests/test_replay_determinism.py tests/test_purity.py

# ---- Faz 2
replay:                  # gerçek kayıt; MAXF=dosya sayısı
	$(PY) -m scripts.replay data/recordings/$(REC) $(if $(MAXF),--max-files $(MAXF),)

# ---- Faz 4
replay-positions:        # statik SL/TP vs kurallı yönetim (bilgilendirici); MAXF, SL, TP, W
	$(PY) -m scripts.replay_positions data/recordings/$(REC) $(if $(MAXF),--max-files $(MAXF),) --sl $(or $(SL),0.5) --tp $(or $(TP),1.0) --W $(or $(W),120) --json-out data/research/replay-positions.json > docs/design/faz4-replay-karsilastirma.md

# ---- Faz 3
export-bars:             # replay → data/research/$(REC)/bars.jsonl ; MAXF opsiyonel
	$(PY) -m scripts.export_bars data/recordings/$(REC) data/research/$(REC)/bars.jsonl $(if $(MAXF),--max-files $(MAXF),)

SYMS ?= BTCUSDT,ETHUSDT,ZECUSDT,SOLUSDT,IOSTUSDT,XRPUSDT,HYPEUSDT,DOGEUSDT,NEARUSDT,BNBUSDT
START ?= 2026-08-09
END ?= 2026-09-09
HIST ?= hist-30d

fetch-history:           # data.binance.vision günlük zip + checksum → data/history/
	$(PY) -m scripts.fetch_history --symbols $(SYMS) --start $(START) --end $(END)

build-history-bars:      # → data/research/$(HIST)/bars.jsonl (çekirdek SymbolMarket ile)
	$(PY) -m scripts.build_history_bars --symbols $(SYMS) --start $(START) --end $(END) --out data/research/$(HIST)/bars.jsonl

research-scan:           # yalnızca keşif bölümü; parametre duyarlılığı
	$(PY) -m scripts.research_scan data/research/$(REC)/bars.jsonl

research-report:         # → docs/research/rapor-$(REC).md
	$(PY) -m scripts.research_report data/research/$(REC)/bars.jsonl --json-out data/research/$(REC)/report.json > docs/research/rapor-$(REC).md

# ---- Faz 0
measure-latency:
	for t in rest_keepalive,rest_newconn ws_public ws_market ws_api; do \
	  nohup $(PY) -m scripts.measure_latency --duration 86400 --run-id $(RUN) --only $$t --ws-sample 10 \
	    > data/latency/$(RUN)/proc_$${t%%,*}.log 2>&1 & \
	done

summarize-latency:
	$(PY) -m scripts.summarize_latency data/latency/$(RUN)

unit-economics:
	$(PY) -m scripts.unit_economics > docs/unit-economics.generated.md

# ---- Faz 1
run-recorder:            # yerel, ön planda; DURATION=saniye opsiyonel
	$(PY) -m fbot.recorder.main --config config/recorder.toml --run-id $(REC) $(if $(DURATION),--duration $(DURATION),)

verify-recording:
	$(PY) -m scripts.verify_recording data/recordings/$(REC)

verify-orderbook:        # local order book replay; MAXF=dosya sayısı, SYMS=btcusdt,ethusdt opsiyonel
	$(PY) -m scripts.verify_orderbook data/recordings/$(REC) $(if $(MAXF),--max-files $(MAXF),) $(if $(SYMS),--symbols $(SYMS),)

docker-build:
	GIT_SHA=$(GIT_SHA) docker compose build

up:                      # 72 saatlik kayıt; volume sahipliği container kullanıcısına (uid 10001)
	mkdir -p data/recordings && chown -R 10001 data/recordings
	GIT_SHA=$(GIT_SHA) FBOT_RUN_ID=$(REC) docker compose up -d recorder

down:
	docker compose down

logs:
	docker compose logs -f --tail=50 recorder
