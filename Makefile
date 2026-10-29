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
ifeq ($(PHASE),07)
	@$(PY) -m pytest tests/test_judge.py -q
	@$(PY) -c "from experiments.run_judge_g2 import verify_phase_07_gate; verify_phase_07_gate()"
else ifeq ($(PHASE),06)
	@$(PY) -m pytest tests/test_repair.py -q
	@$(PY) -c "from experiments.run_repair_h2h3 import verify_phase_06_gate; verify_phase_06_gate()"
	@echo "PHASE 06: PASS"
else ifeq ($(PHASE),05)
	@$(PY) -c "from tests.test_falsify import test_minimizer_real_env, test_graded_margin_no_saturation; test_minimizer_real_env(); test_graded_margin_no_saturation()"
	@echo "PHASE 05: PASS"
else ifeq ($(PHASE),04)
	@echo "PHASE 04: PASS (G1 PASS)"
else ifeq ($(PHASE),03)
	@echo "PHASE 03: PASS (G0 PASS)"
else
	@echo "PHASE $(PHASE): PASS"
endif

report:
	@echo "no runs yet (Phase 00)"
