PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: help tour dev check replay evals lint test clean

help:
	@echo "Targets:"
	@echo "  dev     Install the package with dev extras (ruff, pytest)"
	@echo "  check   Run the local validation gate (scripts/validate-local.sh)"
	@echo "  replay  Run sample routing replay"
	@echo "  evals   Summarize sample routing replay"
	@echo "  lint    ruff check . (if installed)"
	@echo "  test    pytest (if installed)"

tour:
	@echo "Model-routing experiment scaffold"
	@echo "  try  : make check"

dev:
	@$(PY) -m pip install -e ".[dev]"

check:
	@bash scripts/validate-local.sh

replay:
	@$(PY) samples/python/replay_route.py samples/telemetry/mixed-coding-workload.sample.jsonl

evals:
	@$(PY) evals/run.py --workload samples/telemetry/mixed-coding-workload.sample.jsonl --signals samples/responses/routing-signals.sample.json --pricing samples/pricing/illustrative.yaml

lint:
	@ruff check .

test:
	@$(PY) -m pytest

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
