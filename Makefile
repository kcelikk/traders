# fbot — tekrar edilebilir komutlar. Var olmayan hedef yazılmaz.
PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest

.PHONY: setup test

setup:
	python3 -m venv .venv
	$(PIP) install -q -r requirements.txt
	$(PY) -c "import websockets, pytest; print('ok', websockets.__version__, pytest.__version__)"

test:
	$(PYTEST) -q tests
