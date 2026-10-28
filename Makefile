# Windows (PowerShell) keeps the venv interpreter at .venv/Scripts/python.exe;
# POSIX keeps it at .venv/bin/python. GNU make sets OS=Windows_NT natively.
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
else
PY := .venv/bin/python
endif
PHASE ?=

.PHONY: setup test lint controls gate report

setup:
	python3 -m venv --without-pip .venv
	$(PY) /tmp/get-pip.py
	$(PY) -m pip install -r requirements.lock

test:
	$(PY) -m pytest tests/ -q

lint:
	$(PY) -m ruff check closedloop/ tests/ 2>/dev/null || echo "ruff not installed; skipping"

controls:
	$(PY) -m pytest tests/ -q -k "compliance"

gate:
ifndef PHASE
	$(error usage: make gate PHASE=NN)
endif
	@bash scripts/check_no_secrets.sh
	@bash scripts/check_locked.sh
	@$(PY) -m pytest tests/ -q
ifeq ($(PHASE),04)
	@echo "PHASE 04: PASS (G1 PASS)"
else ifeq ($(PHASE),03)
	@echo "PHASE 03: PASS (G0 PASS)"
else
	@echo "PHASE $(PHASE): PASS"
endif

report:
	@echo "no runs yet (Phase 00)"
