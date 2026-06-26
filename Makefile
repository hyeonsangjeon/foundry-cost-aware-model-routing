PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
WORKLOAD ?= samples/telemetry/mixed-coding-workload.sample.jsonl
SIGNALS ?= samples/responses/routing-signals.sample.json
PRICING ?= samples/pricing/illustrative.yaml

.PHONY: help tour dev check replay replay-all evals evals-all lint test clean

help:
	@echo "Targets:"
	@echo "  dev         Install the package with dev extras (ruff, pytest)"
	@echo "  check       Run the local validation gate (scripts/validate-local.sh)"
	@echo "  replay      Run sample routing replay (curated fixture)"
	@echo "  replay-all  Replay the whole workload with deterministic offline signals"
	@echo "  evals       Summarize sample routing replay (curated fixture)"
	@echo "  evals-all   Summarize the whole workload with deterministic offline signals"
	@echo "  lint        ruff check . (if installed)"
	@echo "  test        pytest (if installed)"

tour:
	@echo "Model-routing experiment scaffold"
	@echo "  try  : make check"

dev:
	@$(PY) -m pip install -e ".[dev]"

check:
	@bash scripts/validate-local.sh

replay:
	@$(PY) samples/python/replay_route.py $(WORKLOAD)

replay-all:
	@$(PY) samples/python/replay_route.py $(WORKLOAD) --synth

evals:
	@$(PY) evals/run.py --workload $(WORKLOAD) --signals $(SIGNALS) --pricing $(PRICING)

evals-all:
	@$(PY) evals/run.py --workload $(WORKLOAD) --pricing $(PRICING) --synth

lint:
	@ruff check .

test:
	@$(PY) -m pytest

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
