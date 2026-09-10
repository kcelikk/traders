# fbot — tekrar edilebilir komutlar. Var olmayan hedef yazılmaz.
PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
RUN ?= baseline-24h-20260910
REC ?= rec-72h
GIT_SHA := $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)

.PHONY: setup test test-determinism replay export-bars research-report measure-latency summarize-latency unit-economics run-recorder verify-recording verify-orderbook docker-build up down logs

setup:
	python3 -m venv .venv
	$(PIP) install -q -r requirements-dev.txt
	$(PY) -c "import websockets, pytest; print('ok', websockets.__version__, pytest.__version__)"

test:
	$(PYTEST) -q tests

test-determinism:        # Rule Zero: fixture iki ayrı process'te, hash eşit; mutasyonda farklı
	$(PYTEST) -q tests/test_replay_determinism.py tests/test_purity.py

# ---- Faz 2
replay:                  # gerçek kayıt; MAXF=dosya sayısı
	$(PY) -m scripts.replay data/recordings/$(REC) $(if $(MAXF),--max-files $(MAXF),)

# ---- Faz 3
export-bars:             # replay → data/research/$(REC)/bars.jsonl ; MAXF opsiyonel
	$(PY) -m scripts.export_bars data/recordings/$(REC) data/research/$(REC)/bars.jsonl $(if $(MAXF),--max-files $(MAXF),)

research-report:         # → docs/research/rapor-$(REC).md
	$(PY) -m scripts.research_report data/research/$(REC)/bars.jsonl > docs/research/rapor-$(REC).md

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
