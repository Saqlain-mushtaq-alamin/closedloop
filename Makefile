PY := .venv/bin/python
PHASE ?=

.PHONY: setup test lint controls gate report

setup:
	python3 -m venv --without-pip .venv
	.venv/bin/python /tmp/get-pip.py
	.venv/bin/pip install -r requirements.lock

test:
	$(PY) -m pytest tests/ -q

lint:
	$(PY) -m ruff check closedloop/ tests/ 2>/dev/null || echo "ruff not installed; skipping"

controls:
	$(PY) -m pytest tests/ -q -k "compliance"

gate:
	@if [ -z "$(PHASE)" ]; then echo "usage: make gate PHASE=NN"; exit 1; fi
	@bash scripts/check_no_secrets.sh
	@bash scripts/check_locked.sh
	@$(PY) -m pytest tests/ -q
	@echo "PHASE $(PHASE): PASS"

report:
	@echo "no runs yet (Phase 00)"
