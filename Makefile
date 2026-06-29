PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
WORKLOAD ?= samples/telemetry/mixed-coding-workload.sample.jsonl
SIGNALS ?= samples/responses/routing-signals.sample.json
PRICING ?= samples/pricing/illustrative.yaml
POLICY ?= src/policy/seed_policy.yaml
CANDIDATE ?= samples/policy/candidate.example.yaml
HOST ?= 127.0.0.1
PORT ?= 8000
IMAGE ?= cost-router:local

.PHONY: help tour dev check replay replay-all evals evals-all serve docker-build docker-run policy-validate policy-simulate policy-regression lint test clean

help:
	@echo "Targets:"
	@echo "  dev               Install the package with dev extras (ruff, pytest)"
	@echo "  check             Run the local validation gate (scripts/validate-local.sh)"
	@echo "  replay            Run sample routing replay (curated fixture)"
	@echo "  replay-all        Replay the whole workload with deterministic offline signals"
	@echo "  evals             Summarize sample routing replay (curated fixture)"
	@echo "  evals-all         Summarize the whole workload with deterministic offline signals"
	@echo "  serve             Run the offline routing HTTP service (HOST/PORT overridable)"
	@echo "  docker-build      Build the offline service container image (IMAGE overridable)"
	@echo "  docker-run        Run the service container on PORT"
	@echo "  policy-validate   Validate POLICY against the contract"
	@echo "  policy-simulate   Replay/eval CANDIDATE on the synth workload"
	@echo "  policy-regression Compare CANDIDATE vs POLICY on the synth workload"
	@echo "  lint              ruff check . (if installed)"
	@echo "  test              pytest (if installed)"

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

serve:
	@$(PY) -m router serve --host $(HOST) --port $(PORT)

docker-build:
	@docker build -t $(IMAGE) .

docker-run:
	@docker run --rm -p $(PORT):8000 $(IMAGE)

policy-validate:
	@$(PY) -m router policy validate --policy $(POLICY)

policy-simulate:
	@$(PY) -m router policy simulate --policy $(CANDIDATE) --synth

policy-regression:
	@$(PY) -m router policy regression --base $(POLICY) --candidate $(CANDIDATE) --synth

lint:
	@ruff check .

test:
	@$(PY) -m pytest

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
