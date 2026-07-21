"""Tests for the live Azure AI Foundry arena (``router.foundry_arena``).

Network-free: the Azure SDK call is exercised through an injected fake client
whose behaviour keys off the requested deployment, so the four arms, the
fan-out tax, the per-axis winners, honest labels, model-name normalization and
the measured ledger are all pinned deterministically without egress.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from router import cli
from router.foundry_arena import (
    ArenaTask,
    ArmResult,
    FleetSlate,
    FoundryFleet,
    LiveCall,
    MeasuredArenaLedger,
    arena_report,
    cheapest_arm,
    ensemble_arm,
    load_arena_tasks,
    normalize_model_name,
    premium_arm,
    router_arm,
    run_arena_task,
)
from router.foundry_live import FoundryConfig
from router.ledger import verify_measured_ledger
from router.pricing import PricingTable

ROOT = Path(__file__).resolve().parents[1]
FLEET_PRICING = ROOT / "samples" / "pricing" / "foundry-5series.yaml"
CURATED_LIVE = ROOT / "samples" / "telemetry" / "curated-arena-live.sample.jsonl"

# Underlying model + billed usage each deployment returns in the fake below.
_FAKE = {
    "gpt-5.4-nano": ("gpt-5.4-nano-2026-03-17", 100, 50, 0),
    "gpt-5.4-mini": ("gpt-5.4-mini-2026-03-17", 100, 60, 0),
    "gpt-5.4": ("gpt-5.4-2026-03-05", 100, 80, 0),
    "model-router": ("grok-4-1-fast-reasoning", 100, 0, 200),  # router picks grok
}


class _FakeCompletions:
    def __init__(self) -> None:
        self.last_messages: list[dict[str, str]] | None = None

    def create(self, *, model, messages, **_kwargs):
        self.last_messages = messages
        underlying, prompt_tokens, completion, reasoning = _FAKE[model]
        return SimpleNamespace(
            model=underlying,
            usage=SimpleNamespace(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion + reasoning,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
            ),
        )


def _fleet() -> tuple[FoundryFleet, _FakeCompletions]:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://x.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "k",
        }
    )
    completions = _FakeCompletions()
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return FoundryFleet.from_config(config, sdk_client=sdk), completions


def _pricing() -> PricingTable:
    return PricingTable.from_yaml(FLEET_PRICING)


def _task() -> ArenaTask:
    return ArenaTask(task_id="t-0001", prompt="Implement slugify(title).", title="slugify")


# -- model-name normalization ------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("gpt-5.4-2026-03-05", "gpt-5.4"),
        ("gpt-5.4-mini-2026-03-17", "gpt-5.4-mini"),
        ("grok-4-1-fast-reasoning", "grok-4-1-fast-reasoning"),
        ("gpt-oss-120b", "gpt-oss-120b"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_model_name(raw, expected) -> None:
    assert normalize_model_name(raw) == expected


# -- transport ---------------------------------------------------------------


def test_fleet_call_captures_model_usage_and_latency() -> None:
    fleet, _ = _fleet()
    call = fleet.call("gpt-5.4-nano", _task())
    assert call.deployment == "gpt-5.4-nano"
    assert call.model == "gpt-5.4-nano"  # version suffix stripped
    assert call.usage["input"] == 100 and call.usage["output"] == 50
    assert call.latency_ms >= 0.0
    assert call.provenance == "live"


def test_system_prompt_is_sent_when_present() -> None:
    fleet, completions = _fleet()
    fleet.call("gpt-5.4", ArenaTask("t-x", "do it", system="You are terse."))
    assert completions.last_messages is not None
    assert completions.last_messages[0] == {"role": "system", "content": "You are terse."}
    assert completions.last_messages[-1]["role"] == "user"


# -- arms --------------------------------------------------------------------


def test_single_arms_are_single_call() -> None:
    fleet, _ = _fleet()
    slate, pricing, task = FleetSlate(), _pricing(), _task()
    cheap = cheapest_arm(fleet, task, slate, pricing)
    prem = premium_arm(fleet, task, slate, pricing)
    assert cheap.arm == "cheapest" and cheap.fanout == 1 and cheap.billing == "single-call"
    assert cheap.chosen_model == "gpt-5.4-nano"
    assert prem.chosen_model == "gpt-5.4"
    assert prem.cost_usd > cheap.cost_usd  # frontier costs more than the small tier


def test_router_arm_bills_winner_only_and_reports_underlying_model() -> None:
    fleet, _ = _fleet()
    arm = router_arm(fleet, _task(), FleetSlate(), _pricing())
    assert arm.arm == "router" and arm.billing == "winner-only" and arm.fanout == 1
    assert arm.chosen_model == "grok-4-1-fast-reasoning"


def test_ensemble_arm_sums_the_fanout_tax() -> None:
    fleet, _ = _fleet()
    slate, pricing, task = FleetSlate(), _pricing(), _task()
    arm = ensemble_arm(fleet, task, slate, pricing)
    assert arm.billing == "sum-all-fanout" and arm.fanout == 3
    # tax == sum of the three member call costs
    expected = sum(c.cost_usd(pricing) for c in arm.calls)
    assert arm.cost_usd == pytest.approx(round(expected, 6))
    # keeps the strongest tier's answer
    assert arm.chosen_model == "gpt-5.4"


# -- orchestration -----------------------------------------------------------


def test_run_arena_task_picks_winners_and_labels_measured() -> None:
    fleet, _ = _fleet()
    outcome = run_arena_task(fleet, _task(), FleetSlate(), _pricing())
    assert set(outcome.arms) == {"cheapest", "premium", "ensemble", "router"}
    # cheapest single small-tier call is the cost winner here
    assert outcome.winners["cost"] == "cheapest"
    assert outcome.winners["latency"] in outcome.arms
    assert outcome.labels["measured"] is True
    assert outcome.labels["provenance"] == "live"
    assert outcome.labels["accuracy"] == "ungraded"


def test_arm_measured_flag_requires_all_live() -> None:
    live = LiveCall("d", "m", {"input": 1}, 1.0, provenance="live")
    recorded = LiveCall("d", "m", {"input": 1}, 1.0, provenance="recorded")
    assert ArmResult("a", "s", "d", "m", 1, "single-call", 0.0, 1.0, (live,)).measured is True
    assert ArmResult("a", "s", "d", "m", 1, "single-call", 0.0, 1.0, (recorded,)).measured is False


def test_arena_report_aggregates_mix_and_savings() -> None:
    fleet, _ = _fleet()
    pricing = _pricing()
    outcomes = [run_arena_task(fleet, _task(), FleetSlate(), pricing)]
    report = arena_report(outcomes, pricing)
    assert report["tasks"] == 1
    assert report["labels"]["measured"] is True
    assert report["router_model_mix"] == {"grok-4-1-fast-reasoning": 1}
    assert set(report["arm_totals"]) == {"cheapest", "premium", "ensemble", "router"}
    # router (grok) is cheaper than premium (gpt-5.4) in this fake -> positive savings
    assert report["router_vs_premium_savings_pct"] > 0


# -- inputs & ledger ---------------------------------------------------------


def test_load_arena_tasks_reads_prompts() -> None:
    tasks = load_arena_tasks(CURATED_LIVE)
    assert len(tasks) == 5
    assert tasks[0].task_id == "t-0001"
    assert "slugify" in tasks[0].prompt


def test_measured_ledger_appends_one_row_per_task(tmp_path: Path) -> None:
    fleet, _ = _fleet()
    pricing = _pricing()
    outcomes = [
        run_arena_task(fleet, ArenaTask(f"t-{i}", "do it"), FleetSlate(), pricing) for i in range(3)
    ]
    ledger = MeasuredArenaLedger(path=tmp_path / "arena.jsonl", pricing=pricing)
    for outcome in outcomes:
        ledger.record(outcome)
    assert ledger.flush() == 3
    lines = (tmp_path / "arena.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    row = json.loads(lines[0])
    # the audit envelope wraps the honest arena payload under `outcome`
    assert row["schema_version"] == 1
    assert row["previous_hash"] is None  # first row starts the chain
    assert len(row["record_hash"]) == 64
    assert row["outcome"]["labels"]["measured"] is True
    assert set(row["outcome"]["arms"]) == {"cheapest", "premium", "ensemble", "router"}
    # every row links to the prior one's digest
    assert json.loads(lines[1])["previous_hash"] == row["record_hash"]


def test_measured_ledger_verifies_chain_and_cost_replay(tmp_path: Path) -> None:
    fleet, _ = _fleet()
    pricing = _pricing()
    path = tmp_path / "arena.jsonl"
    ledger = MeasuredArenaLedger(path=path, pricing=pricing)
    for i in range(2):
        ledger.record(run_arena_task(fleet, ArenaTask(f"t-{i}", "do it"), FleetSlate(), pricing))
    ledger.flush()
    # separate flushes keep chaining across appends
    ledger.record(run_arena_task(fleet, ArenaTask("t-2", "do it"), FleetSlate(), pricing))
    ledger.flush()

    report = verify_measured_ledger(path)
    assert report.ok
    assert report.records == 3
    assert report.replayed == 3
    assert report.mismatches == ()


def test_measured_ledger_detects_tampering(tmp_path: Path) -> None:
    fleet, _ = _fleet()
    pricing = _pricing()
    path = tmp_path / "arena.jsonl"
    ledger = MeasuredArenaLedger(path=path, pricing=pricing)
    ledger.record(run_arena_task(fleet, ArenaTask("t-0", "do it"), FleetSlate(), pricing))
    ledger.flush()

    # flip a recorded cost without re-sealing the hash → verification must fail
    row = json.loads(path.read_text(encoding="utf-8"))
    row["outcome"]["arms"]["premium"]["cost_usd"] = 999.0
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record_hash"):
        verify_measured_ledger(path)


# -- CLI guard ---------------------------------------------------------------


def test_cli_foundry_arena_requires_live(capsys: pytest.CaptureFixture[str]) -> None:
    # Without --live the command must refuse (exit 2) rather than fake a measured run.
    rc = cli.main(["foundry", "arena", "--pricing", str(FLEET_PRICING)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "--live" in out

