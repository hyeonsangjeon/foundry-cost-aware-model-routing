"""v2 rate-card wiring into the benchmark / paid measured path (BOLT-03B-2).

These tests pin the contract that the benchmark path prices through the
authoritative v2 composite card (``RateCardV2.composite_cost``) — fail-closed,
router markup, exact alias map — while the offline experiments (01–08) keep
using the legacy v1 ``PricingTable`` unchanged. Everything is network-free: a
scripted fake client returns the resolved provider model + usage, so the whole
five-surface composite contract (dry-run estimate / reservation ceiling /
per-attempt trace / summary / replay) is exercised without egress.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from router.measure import (
    AttemptResult,
    MeasureCandidate,
    RetryPolicy,
    estimate_dry_run,
    replay_measure,
    run_measure,
)
from router.pricing import PricingTable
from router.pricing_engine import (
    V1PricingEngine,
    V2PricingEngine,
    as_engine,
    engine_from_snapshot,
)
from router.rate_card import RateCardV2
from router.run_plan import (
    LocalRunConfig,
    execute_benchmark,
    resolve_run_plan,
)

ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_CARD = ROOT / "samples/pricing/foundry-ext-router.yaml"

# A tiny, fully-controlled v2 card: one aliased router pick (gpt-4.1) and one
# direct-arm model (gpt-5.6-sol) are priced; Claude is deliberately absent so a
# router pick that lands on it is unpriced and fails closed.
V2_CARD_TEXT = """
schema_version: 2
currency: USD
unit_basis: per_1m_tokens
source: unit-test authoritative card
effective_date: 2026-08-05
capture_date: 2026-08-05
region: eastus
sku_meter_basis: GlobalStandard on-demand
applicability_notes: claude omitted on purpose (unpriced, fail-closed)
router_input_markup: "0.14"
alias_map:
  version: 2
  entries:
    gpt-4.1-2025-04-14: gpt-4.1
rates:
  gpt-4.1: {input: "2.0", output: "8.0"}
  gpt-5.6-sol: {input: "1.25", output: "10.0"}
"""

USAGE = {"input": 1000, "cached": 0, "output": 500, "reasoning": 0}

# Hand-computed composite costs for USAGE against V2_CARD_TEXT:
#   router→gpt-4.1 : markup 1000*0.14/1e6 + in 1000*2/1e6 + out 500*8/1e6
COST_ROUTER_GPT41 = 0.00014 + 0.002 + 0.004
#   direct gpt-5.6-sol (NO markup) : in 1000*1.25/1e6 + out 500*10/1e6
COST_DIRECT_SOL = 0.00125 + 0.005


def _v2_card() -> RateCardV2:
    return RateCardV2.from_dict(yaml.safe_load(V2_CARD_TEXT))


def _v2_engine() -> V2PricingEngine:
    return V2PricingEngine(_v2_card())


def _router_arm() -> MeasureCandidate:
    return MeasureCandidate(model="model-router", deployment="model-router-cost", router=True)


def _direct_arm() -> MeasureCandidate:
    return MeasureCandidate(model="gpt-5.6-sol", deployment="gpt-5.6-sol", router=False)


def _workload() -> dict[str, dict[str, Any]]:
    return {"t1": {"task_id": "t1", "prompt": "p", "tokens": dict(USAGE)}}


class RoutedClient:
    """Fake: each deployment resolves to a fixed provider ``model`` + usage."""

    def __init__(self, resolved: dict[str, str], usage: dict[str, Any] | None = None) -> None:
        self.resolved = resolved
        self.usage = usage or dict(USAGE)

    def attempt(self, *, deployment, provider, task):  # noqa: ANN001 - test seam
        model = self.resolved.get(deployment, deployment)
        return AttemptResult(
            http_status=200, model=model, usage=dict(self.usage),
            latency_ms=10.0, provenance="live",
        )


def _run(tmp_path, candidates, client, **kwargs):
    defaults = dict(
        client=client, pricing=_v2_engine(), exp_id="bench",
        run_dir=tmp_path / "RUN", run_id="RUN", n=1,
        retry=RetryPolicy(max_retries=2, base_backoff_ms=1.0),
        sleeper=lambda _s: None,
        clock=(lambda: "2026-08-05T00:00:00.000+00:00"),
        now=datetime(2026, 8, 5, tzinfo=UTC),
    )
    defaults.update(kwargs)
    return run_measure(_workload(), candidates, **defaults)


# --------------------------------------------------------------------------- #
# Plan resolution: the v2 card no longer crashes the benchmark path
# --------------------------------------------------------------------------- #


def _benchmark_config(rate_card: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "template": False,
        "run_mode": "benchmark",
        "foundry": {
            "auth": "entra",
            "endpoint_kind": "azure_openai",
            "azure_openai_endpoint": "https://acme-res.example.com/",
            "api_version": "2024-10-21",
        },
        "arms": [
            {"id": "router-cost", "kind": "model_router", "provider": "openai",
             "requested_model": "model-router", "deployment": "model-router-cost",
             "expected": {"format": "router", "name": "cost", "version": "2025-11"}},
            {"id": "router-balanced", "kind": "model_router", "provider": "openai",
             "requested_model": "model-router", "deployment": "model-router",
             "expected": {"format": "router", "name": "balanced", "version": "2025-11"}},
            {"id": "router-quality", "kind": "model_router", "provider": "openai",
             "requested_model": "model-router", "deployment": "model-router-quality",
             "expected": {"format": "router", "name": "quality", "version": "2025-11"}},
            {"id": "direct-premium", "kind": "direct", "provider": "openai",
             "requested_model": "gpt-5.6-sol", "deployment": "gpt-5.6-sol"},
        ],
        "benchmark": {
            "workload": str(ROOT / "benchmarks/original-coding/tasks.jsonl"),
            "rate_card": rate_card,
            "smoke_authorization_ceiling_usd": None,
            "repetitions": 3,
            "max_output_tokens": 2048,
            "budget_usd": 20.0,
            "random_seed": 20260729,
            "estimand": {
                "analysis_unit": "task", "repeat_aggregation": "mean",
                "denominator_policy": "all-attempted", "failure_policy": "count-as-zero",
                "cost_per_pass_formula": "total_cost / passes", "paired_statistic": "wilcoxon",
            },
            "grader": {"kind": "exec-signals", "version": 1},
            "retry": {"max_retries": 4},
        },
        "privacy": {"retain_raw_prompts": True, "retain_raw_outputs": True},
        "artifacts": {"local_root": "results/local"},
        "display": {"locale": "en"},
    }


def test_v2_card_benchmark_plan_resolves_with_288_cells() -> None:
    mapping = _benchmark_config(str(AUTHORITATIVE_CARD))
    config = LocalRunConfig.from_mapping(mapping, base_dir=ROOT, source=str(ROOT / ".x.yaml"))
    plan = resolve_run_plan(config, env={})
    assert plan.planned_cells == 288  # 24 tasks × 4 arms × 3 repetitions
    pricing = plan.execution["pricing"]
    assert pricing["schema_version"] == 2
    assert pricing["currency"] == "USD"
    assert plan.rate_card_path == str(AUTHORITATIVE_CARD)


# --------------------------------------------------------------------------- #
# Composite pricing: router markup + underlying, direct without markup
# --------------------------------------------------------------------------- #


def test_v2_router_arm_priced_model_is_composite(tmp_path) -> None:
    client = RoutedClient({"model-router-cost": "gpt-4.1-2025-04-14"})
    result = _run(tmp_path, [_router_arm()], client)
    rows = [json.loads(x) for x in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    ok = [r for r in rows if r["http_status"] == 200]
    assert len(ok) == 1
    row = ok[0]
    assert row["cost_usd"] == pytest.approx(COST_ROUTER_GPT41)
    block = row["pricing"]
    assert block["engine"] == "rate_card_v2"
    assert block["priced"] is True
    assert block["pricing_key"] == "gpt-4.1"  # resolved via the exact alias
    assert block["resolved_model"] == "gpt-4.1-2025-04-14"
    assert block["router_arm"] is True
    assert block["router_markup_usd"] == pytest.approx(0.00014)  # markup applied
    assert result.summary["labels"]["cost_basis"] == "composite-rate-card-v2"


def test_v2_direct_arm_has_no_router_markup(tmp_path) -> None:
    client = RoutedClient({"gpt-5.6-sol": "gpt-5.6-sol"})
    result = _run(tmp_path, [_direct_arm()], client)
    rows = [json.loads(x) for x in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    row = next(r for r in rows if r["http_status"] == 200)
    assert row["cost_usd"] == pytest.approx(COST_DIRECT_SOL)
    assert row["pricing"]["router_arm"] is False
    assert row["pricing"]["router_markup_usd"] == 0.0  # direct arms omit the markup


# --------------------------------------------------------------------------- #
# Fail-closed: an unpriced backend (Claude) withholds the amount
# --------------------------------------------------------------------------- #


def test_v2_router_arm_claude_is_unpriced_fail_closed(tmp_path) -> None:
    client = RoutedClient({"model-router-cost": "claude-sonnet-4-5"})
    result = _run(tmp_path, [_router_arm()], client)
    rows = [json.loads(x) for x in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    row = next(r for r in rows if r["http_status"] == 200)
    # The amount itself is withheld — never a fabricated 0.0.
    assert row["cost_usd"] is None
    block = row["pricing"]
    assert block["priced"] is False
    assert block["pricing_key"] is None
    assert "no pinned rate" in (block["reason"] or "")
    cost = result.summary["cost"]
    assert cost["cost_complete"] is False
    assert cost["unpriced_calls"] == 1
    assert cost["savings_claim_allowed"] is False
    # An unpriced arm is never the cheap "best" winner.
    assert cost["total_usd"] == 0.0
    assert cost["savings_pct"] == 0.0


def test_v2_unpriced_arm_excluded_from_savings(tmp_path) -> None:
    # One priced arm + one unpriced arm: savings compares only cost-complete arms.
    client = RoutedClient(
        {"model-router-cost": "claude-sonnet-4-5", "gpt-5.6-sol": "gpt-5.6-sol"}
    )
    result = _run(tmp_path, [_router_arm(), _direct_arm()], client)
    cost = result.summary["cost"]
    assert cost["cost_complete"] is False
    assert cost["by_candidate"]["model-router"]["cost_complete"] is False
    assert cost["by_candidate"]["gpt-5.6-sol"]["cost_complete"] is True
    # best/naive derive only from the priced arm; the unpriced arm never wins.
    assert cost["best_model"] == "gpt-5.6-sol"
    assert cost["naive_model"] == "gpt-5.6-sol"


# --------------------------------------------------------------------------- #
# §8: the composite cost is identical across all five surfaces
# --------------------------------------------------------------------------- #


def test_v2_cost_identical_across_estimate_reserve_trace_summary_replay(tmp_path) -> None:
    card = _v2_card()
    engine = V2PricingEngine(card)
    direct = _direct_arm()

    # (1) dry-run estimate for the direct arm (predictable pick).
    estimate = estimate_dry_run(_workload(), [direct], n=1, pricing=engine)
    est_cost = estimate["per_candidate"][0]["est_cost_usd"]

    # (2) reservation ceiling for the same cell (long-tier, single composite path).
    reservation = card.reservation_cost(
        pricing_key="gpt-5.6-sol", max_input_tokens=1000, max_output_tokens=500,
        include_router_markup=False,
    )

    # (3) per-attempt trace + (4) summary from a real (fake-client) run.
    client = RoutedClient({"gpt-5.6-sol": "gpt-5.6-sol"})
    result = _run(tmp_path, [direct], client)
    rows = [json.loads(x) for x in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    trace_cost = next(r for r in rows if r["http_status"] == 200)["cost_usd"]
    summary_cost = result.summary["cost"]["by_candidate"]["gpt-5.6-sol"]["total_usd"]

    # (5) credential-free replay recomputes byte-identically.
    report = replay_measure(result.run_dir)

    assert est_cost == pytest.approx(COST_DIRECT_SOL)
    assert float(reservation.total_usd) == pytest.approx(COST_DIRECT_SOL)
    assert trace_cost == pytest.approx(COST_DIRECT_SOL)
    assert summary_cost == pytest.approx(COST_DIRECT_SOL)
    assert report.summary_matches is True
    assert report.cost_mismatches == ()


def test_v2_replay_roundtrips_and_snapshot_rebuilds_v2_engine(tmp_path) -> None:
    client = RoutedClient({"model-router-cost": "gpt-4.1-2025-04-14"})
    result = _run(tmp_path, [_router_arm()], client)
    snapshot_text = (result.run_dir / "pricing.snapshot.yaml").read_text()
    rebuilt = engine_from_snapshot(snapshot_text)
    assert isinstance(rebuilt, V2PricingEngine)
    assert rebuilt.version == 2
    # Two runs are byte-identical (deterministic v2 pricing).
    other = _run(tmp_path / "b", [_router_arm()], RoutedClient(
        {"model-router-cost": "gpt-4.1-2025-04-14"}))
    assert (result.run_dir / "traces.jsonl").read_bytes() == \
        (other.run_dir / "traces.jsonl").read_bytes()
    assert (result.run_dir / "summary.json").read_bytes() == \
        (other.run_dir / "summary.json").read_bytes()


def test_v2_end_to_end_execute_benchmark_uses_composite(tmp_path) -> None:
    # Write the small controlled card next to a temp config and drive the whole
    # run_plan → execute_benchmark → run_measure path with a fake client.
    card_path = tmp_path / "card.yaml"
    card_path.write_text(V2_CARD_TEXT, encoding="utf-8")
    mapping = _benchmark_config(str(card_path))
    mapping["arms"] = [
        {"id": "router-cost", "kind": "model_router", "provider": "openai",
         "requested_model": "model-router", "deployment": "model-router-cost",
         "expected": {"format": "router", "name": "cost", "version": "2025-11"}},
        {"id": "direct-premium", "kind": "direct", "provider": "openai",
         "requested_model": "gpt-5.6-sol", "deployment": "gpt-5.6-sol"},
    ]
    mapping["benchmark"]["workload"] = str(ROOT / "benchmarks/original-coding/tasks.jsonl")
    config = LocalRunConfig.from_mapping(
        mapping, base_dir=tmp_path, source=str(tmp_path / "c.yaml")
    )
    plan = resolve_run_plan(config, env={})
    client = RoutedClient(
        {"model-router-cost": "gpt-4.1-2025-04-14", "gpt-5.6-sol": "gpt-5.6-sol"}
    )
    result = execute_benchmark(
        config, plan, client=client, run_dir=tmp_path / "RUN",
        clock=(lambda: "2026-08-05T00:00:00.000+00:00"),
        now=datetime(2026, 8, 5, tzinfo=UTC), sleeper=lambda _s: None,
    )
    assert result.summary["labels"]["cost_basis"] == "composite-rate-card-v2"
    router = result.summary["cost"]["by_candidate"]["model-router"]
    assert router["avg_usd_per_call"] == pytest.approx(COST_ROUTER_GPT41)  # markup applied
    assert router["cost_complete"] is True
    # replay of the sealed benchmark snapshot is byte-identical.
    report = replay_measure(result.run_dir)
    assert report.summary_matches is True
    assert report.cost_mismatches == ()


# --------------------------------------------------------------------------- #
# Coexistence: the offline v1 path is untouched (fail-open, no markup)
# --------------------------------------------------------------------------- #


def test_v1_pricing_table_wraps_to_v1_engine_unchanged() -> None:
    table = PricingTable.from_yaml(ROOT / "samples/pricing/foundry-5series.yaml")
    engine = as_engine(table)
    assert isinstance(engine, V1PricingEngine)
    assert engine.version == table.version
    # v1 prices by the arm's declared model, never unpriced, emits no v2 columns.
    priced = engine.price(_router_arm(), resolved_model="claude-sonnet-4-5", usage=USAGE)
    assert priced.priced is True
    assert priced.cost_usd == table.cost_usd("model-router", USAGE)
    assert priced.trace_fields() == {}


def test_v1_card_still_resolves_in_plan(tmp_path) -> None:
    # A legacy v1 card (models + default, revision `version`) keeps working.
    card = tmp_path / "v1.yaml"
    card.write_text(
        "version: 7\ncurrency: USD\nsource: legacy\neffective_date: 2026-08-01\n"
        "models:\n  gpt-5.6-sol: {input: 1.25, cached: 0.6, output: 10.0, reasoning: 10.0}\n"
        "  model-router: {input: 3.0, cached: 1.5, output: 10.0, reasoning: 10.0}\n"
        "default: {input: 1.0, cached: 0.5, output: 2.0, reasoning: 2.0}\n",
        encoding="utf-8",
    )
    mapping = _benchmark_config(str(card))
    config = LocalRunConfig.from_mapping(
        mapping, base_dir=tmp_path, source=str(tmp_path / "c.yaml")
    )
    plan = resolve_run_plan(config, env={})
    assert plan.execution["pricing"]["schema_version"] == 7  # revision preserved, not a schema
    assert plan.planned_cells == 288
