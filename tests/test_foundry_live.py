"""Tests for the live Azure AI Foundry Model Router bridge (``router.foundry_live``).

These never touch the network: the Azure SDK call is exercised through an injected
mock client, and the measured scoring path is pinned against a recorded
provider-usage snapshot. The suite guards three promises — config secrets are
never leaked, ``measured = true`` is reserved for a genuinely live call, and cost
is priced from *real* usage rather than the synthetic task tokens.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from policy import load_default_policy
from router import cli
from router.baseline import model_router_summary
from router.foundry_live import (
    DEFAULT_API_VERSION,
    AzureModelRouterClient,
    FoundryConfig,
    RecordedRouterClient,
    RouterOutcome,
    load_recorded_usage,
    measured_router_summary,
)
from router.offline import load_workload
from router.pipeline import _signals_for, resolve_paths
from router.pricing import PricingTable

ROOT = Path(__file__).resolve().parents[1]
USAGE_FIXTURE = ROOT / "samples" / "responses" / "model-router-usage.sample.json"

# Numbers pinned from the recorded snapshot vs. the offline difficulty-tiered proxy.
RECORDED_COST = 0.15673
RECORDED_COVERAGE = 1.0
OFFLINE_PROJECTION_COST = 0.08703


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def bundled():
    """Offline curated workload/signals/policy/pricing (the demo frontier subset)."""

    policy = load_default_policy()
    paths = resolve_paths(root=None)
    workload = load_workload(paths["workload"])
    pricing = PricingTable.from_yaml(paths["pricing"])
    signals = _signals_for(
        synth=False, workload=workload, policy=policy, signals_path=paths["signals"]
    )
    wl = {k: workload[k] for k in signals if k in workload}
    return wl, signals, policy, pricing


def _mock_sdk(
    model: str, *, prompt_tokens: int, completion_tokens: int, cached: int, reasoning: int
):
    """Build a stand-in Azure OpenAI client with one canned chat completion."""

    response = SimpleNamespace(
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
        ),
    )
    completions = SimpleNamespace(create=lambda **_kwargs: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


# -- config: never leak secrets, report readiness ---------------------------


def test_config_status_redacts_every_secret() -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": (
                "https://secret-resource.example/openai/deployments/"
                "model-router/chat/completions?api-version=2024-10-21"
            ),
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "supersecretkey1234ABCD",
            "AZURE_AI_FOUNDRY_CONNECTION_STRING": "InstrumentationKey=leaky-9999",
        }
    )
    status = config.status()
    blob = json.dumps(status)
    assert "supersecretkey" not in blob
    assert "leaky-9999" not in blob
    assert status["api_key"] == "set (****ABCD)"
    assert status["connection_string"] == "set (****9999)"
    # endpoint is reduced to scheme+host (no path, no query)
    assert status["endpoint"] == "https://secret-resource.example"
    assert status["measured"] is False
    assert config.router_configured and config.credentialed


def test_config_reports_missing_and_is_not_credentialed() -> None:
    config = FoundryConfig.from_env({})
    status = config.status()
    assert config.router_configured is False
    assert config.credentialed is False
    assert status["api_key"] == "missing"
    assert "AZURE_AI_FOUNDRY_ENDPOINT" in status["missing"]
    assert "AZURE_AI_FOUNDRY_MODEL_ROUTER" in status["missing"]
    assert "AZURE_AI_FOUNDRY_API_KEY" in status["missing"]


def test_config_reads_both_documented_variable_names() -> None:
    generic = FoundryConfig.from_env(
        {
            "AZURE_OPENAI_ENDPOINT": "https://alt.example/",
            "AZURE_MODEL_ROUTER_DEPLOYMENT": "router-alt",
            "AZURE_OPENAI_API_KEY": "k",
            "AZURE_OPENAI_API_VERSION": "2025-01-01",
        }
    )
    assert generic.endpoint == "https://alt.example/"
    assert generic.deployment == "router-alt"
    assert generic.resolved_api_version == "2025-01-01"


def test_config_default_api_version() -> None:
    assert FoundryConfig.from_env({}).resolved_api_version == DEFAULT_API_VERSION


# -- recorded usage snapshot ------------------------------------------------


def test_load_recorded_usage_parses_outcomes() -> None:
    outcomes = load_recorded_usage(USAGE_FIXTURE)
    assert set(outcomes) == {"t-0001", "t-0003", "t-0004", "t-0005", "t-0006"}
    first = outcomes["t-0001"]
    assert first.model == "balanced-pro"
    assert first.provenance == "recorded"
    assert first.usage["input"] == 1300.0


def test_load_recorded_usage_accepts_a_bare_mapping(tmp_path: Path) -> None:
    path = tmp_path / "bare.json"
    path.write_text(
        json.dumps({"t-0001": {"model": "mini-fast", "usage": {"input": 10}}}),
        encoding="utf-8",
    )
    outcomes = load_recorded_usage(path)
    assert outcomes["t-0001"].model == "mini-fast"
    assert outcomes["t-0001"].provenance == "recorded"


def test_router_outcome_prices_real_usage_with_aliases() -> None:
    pricing = PricingTable.from_yaml(ROOT / "samples" / "pricing" / "illustrative.yaml")
    outcome = RouterOutcome(model="gpt-4o", usage={"input": 1000, "output": 500})
    aliased = outcome.cost_usd(pricing, model_aliases={"gpt-4o": "balanced-pro"})
    direct = outcome.cost_usd(pricing)  # unknown model -> pricing default
    assert aliased != direct
    expected = pricing.cost_usd("balanced-pro", {"input": 1000, "output": 500})
    assert aliased == pytest.approx(expected)


# -- measured scoring path --------------------------------------------------


def test_measured_summary_prices_the_recorded_snapshot(bundled) -> None:
    wl, signals, policy, pricing = bundled
    client = RecordedRouterClient(load_recorded_usage(USAGE_FIXTURE))
    result = measured_router_summary(wl, signals, policy, pricing, client=client)
    assert result["total_cost_usd"] == pytest.approx(RECORDED_COST, abs=1e-6)
    assert result["coverage"] == pytest.approx(RECORDED_COVERAGE)
    assert result["selection"] == "azure-model-router"
    assert result["labels"] == {
        "measured": False,
        "spend_source": "provider-usage",
        "provenance": "recorded",
        "coverage_measured": False,
    }


def test_measured_spend_differs_from_the_offline_projection(bundled) -> None:
    wl, signals, policy, pricing = bundled
    client = RecordedRouterClient(load_recorded_usage(USAGE_FIXTURE))
    measured = measured_router_summary(wl, signals, policy, pricing, client=client)
    offline = model_router_summary(wl, signals, policy, pricing)
    # the whole point: real usage is priced, not the synthetic task tokens
    assert offline["total_cost_usd"] == pytest.approx(OFFLINE_PROJECTION_COST, abs=1e-6)
    assert measured["total_cost_usd"] != pytest.approx(offline["total_cost_usd"], abs=1e-6)


def test_measured_true_only_for_a_live_call(bundled) -> None:
    wl, signals, policy, pricing = bundled

    class LiveClient:
        def complete(self, task):
            return RouterOutcome(
                model="balanced-pro",
                usage={"input": 1000, "output": 300},
                provenance="live",
            )

    result = measured_router_summary(wl, signals, policy, pricing, client=LiveClient())
    assert result["labels"]["measured"] is True
    assert result["labels"]["provenance"] == "live"


def test_grader_makes_coverage_measured(bundled) -> None:
    wl, signals, policy, pricing = bundled
    client = RecordedRouterClient(load_recorded_usage(USAGE_FIXTURE))
    result = measured_router_summary(
        wl, signals, policy, pricing, client=client, grader=lambda _tid, _task, _out: True
    )
    assert result["labels"]["coverage_measured"] is True
    assert result["coverage"] == pytest.approx(1.0)
    assert result["graded"] == result["tasks"]


def test_model_aliases_translate_provider_names(bundled) -> None:
    wl, signals, policy, pricing = bundled

    class AliasClient:
        def complete(self, task):
            return RouterOutcome(
                model="gpt-4o", usage={"input": 1000, "output": 300}, provenance="live"
            )

    result = measured_router_summary(
        wl, signals, policy, pricing, client=AliasClient(), model_aliases={"gpt-4o": "balanced-pro"}
    )
    assert set(result["model_counts"]) == {"balanced-pro"}


# -- the live Azure client (mocked SDK) -------------------------------------


def test_azure_client_raises_without_credentials() -> None:
    client = AzureModelRouterClient(config=FoundryConfig.from_env({}))
    with pytest.raises(RuntimeError, match="not credentialed"):
        client.complete({"prompt": "hi"})


def test_azure_client_maps_response_usage_and_marks_live() -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://x.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "k",
        }
    )
    sdk = _mock_sdk("gpt-4o", prompt_tokens=1000, completion_tokens=300, cached=200, reasoning=120)
    client = AzureModelRouterClient(config=config, sdk_client=sdk)
    outcome = client.complete({"task_id": "t-1", "prompt": "Write a function"})
    assert outcome.model == "gpt-4o"
    assert outcome.provenance == "live"
    # output excludes reasoning; cached never exceeds input
    assert outcome.usage == {"input": 1000.0, "cached": 200.0, "output": 180.0, "reasoning": 120.0}


def test_azure_client_requires_a_prompt() -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://x.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "k",
        }
    )
    sdk = _mock_sdk("gpt-4o", prompt_tokens=1, completion_tokens=1, cached=0, reasoning=0)
    client = AzureModelRouterClient(config=config, sdk_client=sdk)
    with pytest.raises(ValueError, match="no prompt"):
        client.complete({"task_id": "t-1", "tokens": {"input": 100}})


def test_azure_client_accepts_a_messages_list() -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://x.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "k",
        }
    )
    sdk = _mock_sdk("gpt-4o", prompt_tokens=5, completion_tokens=5, cached=0, reasoning=0)
    client = AzureModelRouterClient(config=config, sdk_client=sdk)
    outcome = client.complete({"messages": [{"role": "user", "content": "hello"}]})
    assert outcome.model == "gpt-4o"


def test_recorded_client_raises_on_unknown_task() -> None:
    client = RecordedRouterClient({})
    with pytest.raises(KeyError):
        client.complete({"task_id": "missing"})


# -- CLI ---------------------------------------------------------------------


def test_cli_foundry_status_json_is_redacted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", "https://x.example/")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_MODEL_ROUTER", "model-router")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_API_KEY", "topsecretVALUE")
    assert cli.main(["foundry", "status", "--json"]) == 0
    out = capsys.readouterr().out
    assert "topsecretVALUE" not in out
    assert json.loads(out)["credentialed"] is True


def test_cli_foundry_live_recorded_records_to_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "history.jsonl"
    assert cli.main(["foundry", "live", "--store", str(store)]) == 0
    assert "measured spend" in capsys.readouterr().out
    rows = [json.loads(line) for line in store.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1
    assert rows[0]["experiment"] == "foundry-live"
    assert rows[0]["measured"] is False
    assert rows[0]["routed_usd"] == pytest.approx(RECORDED_COST, abs=1e-6)


def test_cli_foundry_live_json_reports_provenance(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["foundry", "live", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["labels"]["provenance"] == "recorded"
    assert payload["labels"]["measured"] is False
