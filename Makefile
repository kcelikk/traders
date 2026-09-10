# fbot — tekrar edilebilir komutlar. Var olmayan hedef yazılmaz.
PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
RUN ?= baseline-24h-20260910

.PHONY: setup test measure-latency summarize-latency unit-economics

setup:
	python3 -m venv .venv
	$(PIP) install -q -r requirements.txt
	$(PY) -c "import websockets, pytest; print('ok', websockets.__version__, pytest.__version__)"

test:
	$(PYTEST) -q tests

# 24 saatlik ölçüm: kategori başına ayrı process (yerel kuyruklanma ölçüme karışmasın)
measure-latency:
	for t in rest_keepalive,rest_newconn ws_public ws_market ws_api; do \
	  nohup $(PY) -m scripts.measure_latency --duration 86400 --run-id $(RUN) --only $$t --ws-sample 10 \
	    > data/latency/$(RUN)/proc_$${t%%,*}.log 2>&1 & \
	done

summarize-latency:
	$(PY) -m scripts.summarize_latency data/latency/$(RUN)

unit-economics:
	$(PY) -m scripts.unit_economics > docs/unit-economics.generated.md
