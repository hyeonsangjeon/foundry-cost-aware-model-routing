"""Pin experiment 07 (routing layer — Azure AI Foundry Model Router arm): the
single-call ``model_router`` strategy, the ``min_escalation_gain`` reproducibility
contract, and the gated, dependency-free live adapter (the measured bridge).

Every number here is an offline projection (``labels.measured = false``): the arm
is a transparent difficulty-tiered proxy for a single-call router's *shape*, not a
copy of Azure's internal logic. The point of the experiment is the honest gap —
committing to one model per prompt loses coverage that observe-then-escalate keeps.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from policy import load_default_policy
from router import cli
from router.baseline import (
    model_router_pick,
    model_router_summary,
    score_single_call_arm,
)
from router.experiment import _evaluate, list_experiments, load_experiment, run_experiment
from router.foundry_live import RouterOutcome
from router.foundry_router import (
    FOUNDRY_ROUTER_ENV_VARS,
    FoundryModelRouter,
    azure_router_choice_client,
    capture_recorded_choices,
    live_router_summary,
    load_recorded_choices,
    summary_from_choices,
)
from router.offline import load_workload
from router.pipeline import _signals_for, resolve_paths, run_bundled_replay
from router.pricing import PricingTable

ROOT = Path(__file__).resolve().parents[1]
CHOICES_FIXTURE = ROOT / "samples" / "responses" / "model-router-choices.sample.json"


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def bundled():
    """Offline curated workload/signals/policy/pricing used by the demo frontier."""

    policy = load_default_policy()
    paths = resolve_paths(root=None)
    workload = load_workload(paths["workload"])
    pricing = PricingTable.from_yaml(paths["pricing"])
    signals = _signals_for(
        synth=False, workload=workload, policy=policy, signals_path=paths["signals"]
    )
    wl = {k: workload[k] for k in signals if k in workload}
    return wl, signals, policy, pricing


# -- the arm: a deterministic single-call routing layer ---------------------


def test_model_router_arm_is_deterministic_on_synth() -> None:
    st = run_bundled_replay(synth=True).summary["strategies"]["model_router"]
    # single-call commit: cheaper than premium, but well short of full coverage
    assert st["total_cost_usd"] == pytest.approx(1.587646, abs=1e-6)
    assert st["coverage"] == pytest.approx(0.52)
    assert st["selection"] == "difficulty-tiered-single-call"
    assert st["labels"] == {"measured": False, "equivalent": "illustrative"}


def test_model_router_arm_is_deterministic_on_curated() -> None:
    st = run_bundled_replay(synth=False).summary["strategies"]["model_router"]
    assert st["total_cost_usd"] == pytest.approx(0.087030, abs=1e-6)
    assert st["coverage"] == pytest.approx(0.6)


def test_frontier_has_five_strategy_arms() -> None:
    st = run_bundled_replay(synth=True).summary["strategies"]
    assert set(st) == {"all_mini", "all_premium", "all_ensemble", "model_router", "mix"}


def test_model_router_sits_between_mini_and_the_full_coverage_arms() -> None:
    st = run_bundled_replay(synth=True).summary["strategies"]
    router = st["model_router"]
    # off the both-win corner: pricier than all-mini, yet below full coverage
    assert st["all_mini"]["total_cost_usd"] < router["total_cost_usd"]
    assert router["coverage"] < st["mix"]["coverage"]
    assert router["coverage"] < 1.0


def test_pick_is_a_pure_floor_over_the_ladder() -> None:
    policy = load_default_policy()
    from router.classify import classify_task

    task = {"task_id": "t", "class": "generate", "difficulty": "hard"}
    candidates = policy.candidates_for(classify_task(task))
    pick = model_router_pick(task, candidates)
    # hard task -> top of that class's ladder; deterministic and in-range
    assert pick is candidates[-1]
    assert model_router_pick({"class": "generate", "difficulty": "easy"}, candidates) is (
        candidates[0]
    )


def test_score_single_call_arm_honours_a_custom_pick(bundled) -> None:
    wl, signals, policy, pricing = bundled
    # always-cheapest pick -> matches the all-mini corner story (low cost, low cover)
    cheapest = score_single_call_arm(
        wl, signals, policy, pricing, pick=lambda tid, task, cands: cands[0]
    )
    assert cheapest["total_cost_usd"] == pytest.approx(0.010788, abs=1e-6)
    assert cheapest["coverage"] == pytest.approx(0.4)
    assert cheapest["tasks"] == 5


# -- the contract: min_escalation_gain --------------------------------------


def test_model_router_experiment_is_registered_with_the_gain_floor() -> None:
    assert "model-router" in [experiment.name for experiment in list_experiments()]
    exp = load_experiment("model-router")
    assert exp.expect.min_escalation_gain == pytest.approx(0.30)
    assert exp.expect.min_coverage == pytest.approx(1.0)
    assert exp.expect.min_tasks == 100


def test_min_escalation_gain_round_trips_through_to_dict() -> None:
    payload = load_experiment("model-router").to_dict()
    assert payload["expect"]["min_escalation_gain"] == pytest.approx(0.30)


def test_experiment_without_the_field_omits_the_check() -> None:
    # hero-style experiments set no gain floor -> the check is not emitted
    result = run_experiment(load_experiment("curated"))
    assert "escalation_gain" not in {check.name for check in result.checks}


def test_escalation_gain_contract_is_green() -> None:
    result = run_experiment(load_experiment("model-router"))
    assert result.ok is True
    gain = next(c for c in result.checks if c.name == "escalation_gain")
    assert gain.ok is True
    # mix 100% − single-call 52% = +48% ≥ the 30% floor
    assert "48.0%" in gain.detail


def test_escalation_gain_bites_when_the_floor_is_raised() -> None:
    exp = load_experiment("model-router")
    result = run_experiment(exp)
    strict = dataclasses.replace(exp.expect, min_escalation_gain=0.60)
    checks = _evaluate(result.report, strict)
    gain = next(c for c in checks if c.name == "escalation_gain")
    assert gain.ok is False


# -- the measured bridge: gated live adapter --------------------------------


def test_adapter_is_inert_without_configuration() -> None:
    router = FoundryModelRouter.from_env(env={})
    assert router.configured is False
    assert router.available is False
    with pytest.raises(RuntimeError, match="not available"):
        router.choose({"task_id": "t"})


def test_adapter_is_configured_but_unavailable_without_a_client() -> None:
    env = {
        "AZURE_AI_FOUNDRY_ENDPOINT": "https://foundry.example/endpoint",
        "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
    }
    router = FoundryModelRouter.from_env(env=env)
    assert router.configured is True
    assert router.available is False  # no client injected -> still no egress


def test_adapter_from_env_reads_the_documented_variables() -> None:
    assert "AZURE_AI_FOUNDRY_ENDPOINT" in FOUNDRY_ROUTER_ENV_VARS["endpoint"]
    assert "AZURE_AI_FOUNDRY_MODEL_ROUTER" in FOUNDRY_ROUTER_ENV_VARS["deployment"]
    env = {
        "AZURE_OPENAI_ENDPOINT": "https://foundry.example/fallback",
        "AZURE_MODEL_ROUTER_DEPLOYMENT": "router-v1",
        "AZURE_OPENAI_API_KEY": "placeholder-not-a-real-key",
    }
    router = FoundryModelRouter.from_env(env=env, client=lambda dep, task: "mini-fast")
    assert router.endpoint == "https://foundry.example/fallback"
    assert router.deployment == "router-v1"
    assert router.available is True
    assert router.choose({"task_id": "t"}) == "mini-fast"


# -- recorded / live choices scored on the same offline frontier ------------


def test_recorded_choices_fixture_scores_deterministically(bundled) -> None:
    wl, signals, policy, pricing = bundled
    choices = load_recorded_choices(CHOICES_FIXTURE)
    result = summary_from_choices(wl, signals, policy, pricing, choices)
    # this recorded run leaned strong: full coverage, but 2.3x the escalating mix
    assert result["total_cost_usd"] == pytest.approx(0.127136, abs=1e-6)
    assert result["coverage"] == pytest.approx(1.0)
    assert result["selection"] == "foundry-model-router"
    assert result["labels"] == {"measured": False, "decisions": "recorded"}


def test_load_recorded_choices_accepts_a_bare_mapping(tmp_path: Path) -> None:
    path = tmp_path / "bare.json"
    path.write_text(json.dumps({"t-0001": "mini-fast"}), encoding="utf-8")
    assert load_recorded_choices(path) == {"t-0001": "mini-fast"}


def test_unknown_choice_falls_back_to_the_offline_pick(bundled) -> None:
    wl, signals, policy, pricing = bundled
    # a model that is not a candidate must not crash — it falls back to the proxy
    result = summary_from_choices(wl, signals, policy, pricing, {"t-0001": "nonexistent"})
    offline = model_router_summary(wl, signals, policy, pricing)
    assert result["total_cost_usd"] == pytest.approx(offline["total_cost_usd"], abs=1e-9)
    assert result["tasks"] == 5


def test_live_router_summary_records_live_provenance(bundled) -> None:
    wl, signals, policy, pricing = bundled
    choices = load_recorded_choices(CHOICES_FIXTURE)
    router = FoundryModelRouter(
        endpoint="https://x",
        deployment="model-router",
        client=lambda dep, task: choices[task["task_id"]],
    )
    result = live_router_summary(wl, signals, policy, pricing, router)
    assert result["total_cost_usd"] == pytest.approx(0.127136, abs=1e-6)
    assert result["labels"]["decisions"] == "live"


# -- the real-Azure choice seam: adapter + capture --------------------------


class _StubRouterClient:
    """A fake AzureModelRouterClient: echoes a version-suffixed name + deployment."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def complete(self, task, *, deployment=None):
        self.seen.append(str(deployment))
        return RouterOutcome(
            model="gpt-5.4-2026-03-05",
            usage={"input": 10, "output": 5},
            provenance="live",
        )


def test_azure_router_choice_client_bridges_and_normalizes() -> None:
    client = _StubRouterClient()
    choose = azure_router_choice_client(client)
    assert choose("model-router", {"task_id": "t-0003", "prompt": "p"}) == "gpt-5.4"
    assert client.seen == ["model-router"]  # deployment threaded through


def test_azure_router_choice_client_can_preserve_raw_names() -> None:
    choose = azure_router_choice_client(_StubRouterClient(), normalize=False)
    assert choose("model-router", {"task_id": "t", "prompt": "p"}) == "gpt-5.4-2026-03-05"


def test_capture_recorded_choices_builds_a_live_snapshot() -> None:
    router = FoundryModelRouter(
        endpoint="https://x",
        deployment="model-router",
        client=azure_router_choice_client(_StubRouterClient()),
    )
    # keys deliberately unsorted to prove the capture orders them
    workload = {"t-0002": {"task_id": "t-0002", "prompt": "b"},
                "t-0001": {"task_id": "t-0001", "prompt": "a"}}
    snapshot = capture_recorded_choices(workload, router, resource={"account": "aoai-x"})
    assert snapshot["version"] == 1
    assert snapshot["labels"] == {
        "measured": False,
        "decisions": "recorded",
        "captured_from": "live",
    }
    assert snapshot["captured_at"].endswith("+00:00")  # ISO-8601 UTC
    assert snapshot["resource"] == {"account": "aoai-x"}
    assert list(snapshot["choices"]) == ["t-0001", "t-0002"]
    assert snapshot["choices"]["t-0001"] == "gpt-5.4"  # date suffix normalized away


def test_capture_recorded_choices_round_trips(tmp_path: Path) -> None:
    router = FoundryModelRouter(
        endpoint="https://x",
        deployment="model-router",
        client=azure_router_choice_client(_StubRouterClient()),
    )
    snapshot = capture_recorded_choices({"t-0001": {"task_id": "t-0001", "prompt": "a"}}, router)
    path = tmp_path / "choices.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    assert load_recorded_choices(path) == {"t-0001": "gpt-5.4"}


# -- the CLI: `foundry router` single-call head-to-head ---------------------


def test_cli_foundry_router_offline_compares_proxy_and_choices(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["foundry", "router"]) == 0
    out = capsys.readouterr().out
    assert "offline proxy pick" in out
    assert "router choices" in out
    assert "decisions: recorded" in out
    assert "measured=no" in out


def test_cli_foundry_router_json_reports_both_arms(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["foundry", "router", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["proxy"]["selection"] == "difficulty-tiered-single-call"
    assert payload["router_choices"]["selection"] == "foundry-model-router"
    assert payload["router_choices"]["labels"]["decisions"] == "recorded"
    assert payload["router_choices"]["total_cost_usd"] == pytest.approx(0.127136, abs=1e-6)


def test_cli_foundry_router_capture_requires_live(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dest = tmp_path / "choices.json"
    assert cli.main(["foundry", "router", "--capture", str(dest)]) == 2
    assert "needs live calls" in capsys.readouterr().out
    assert not dest.exists()
