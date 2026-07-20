"""Tests for the live Azure AI Foundry Model Router bridge (``router.foundry_live``).

These never touch the network: the Azure SDK call is exercised through an injected
mock client, and the measured scoring path is pinned against a recorded
provider-usage snapshot. The suite guards three promises — config secrets are
never leaked, ``measured = true`` is reserved for a genuinely live call, and cost
is priced from *real* usage rather than the synthetic task tokens.
"""

from __future__ import annotations

import json
import sys
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
    load_dotenv_file,
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


def _canned_response(model: str):
    """A minimal chat-completion response with usage the pricer can read."""

    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=200,
            completion_tokens=80,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch, response) -> dict:
    """Install a fake ``openai`` module so ``_sdk_client`` builds without network.

    Returns a dict capturing the ``AzureOpenAI(...)`` constructor kwargs, so a
    test can assert whether key auth or an Entra token provider was wired.
    """

    captured: dict = {}

    class FakeAzureOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_k: response)
            )

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AzureOpenAI=FakeAzureOpenAI))
    return captured


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


# -- curated live workload: the one-command flip to measured -----------------

CURATED_LIVE_WORKLOAD = ROOT / "samples" / "telemetry" / "curated-arena-live.sample.jsonl"
CURATED_TASK_IDS = {"t-0001", "t-0003", "t-0004", "t-0005", "t-0006"}


def test_curated_live_workload_is_sendable() -> None:
    """Every curated task carries a real prompt, so the live bridge can send it.

    The bundled synthetic telemetry has no prompt text and cannot be measured
    live; this workload is the ready-made, live-sendable subset for the arena.
    """

    wl = load_workload(CURATED_LIVE_WORKLOAD)
    assert set(wl) == CURATED_TASK_IDS
    for task in wl.values():
        assert task.get("prompt", "").strip()  # _messages_for would succeed


def test_curated_workload_scores_recorded_snapshot_offline() -> None:
    """Replaying the recorded snapshot over the curated workload stays measured=false."""

    wl = load_workload(CURATED_LIVE_WORKLOAD)
    policy = load_default_policy()
    paths = resolve_paths(root=None)
    pricing = PricingTable.from_yaml(paths["pricing"])
    signals = _signals_for(synth=False, workload=wl, policy=policy, signals_path=paths["signals"])
    client = RecordedRouterClient(load_recorded_usage(USAGE_FIXTURE))
    result = measured_router_summary(wl, signals, policy, pricing, client=client)
    assert result["tasks"] == len(CURATED_TASK_IDS)
    assert result["labels"]["measured"] is False
    assert result["labels"]["provenance"] == "recorded"


def test_curated_workload_live_call_sends_prompts_and_measures() -> None:
    """With credentials (mocked here) the curated workload flips to measured=true.

    Proves the one-command promise: the live client sends each task's real prompt
    and prices the response's real usage, so the summary is measured = true.
    """

    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://x.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "k",
        }
    )
    sent: list[str] = []

    class _Recording:
        def create(self, *, model, messages, **_kwargs):
            sent.append(messages[-1]["content"])
            return SimpleNamespace(
                model="gpt-4o-mini",
                usage=SimpleNamespace(
                    prompt_tokens=1200,
                    completion_tokens=400,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=300),
                    completion_tokens_details=SimpleNamespace(reasoning_tokens=150),
                ),
            )

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=_Recording()))
    client = AzureModelRouterClient(config=config, sdk_client=sdk)

    wl = load_workload(CURATED_LIVE_WORKLOAD)
    policy = load_default_policy()
    paths = resolve_paths(root=None)
    pricing = PricingTable.from_yaml(paths["pricing"])
    signals = _signals_for(synth=False, workload=wl, policy=policy, signals_path=paths["signals"])
    result = measured_router_summary(
        wl, signals, policy, pricing, client=client, model_aliases={"gpt-4o-mini": "mini-fast"}
    )
    assert len(sent) == len(CURATED_TASK_IDS)
    assert any("slugify" in prompt for prompt in sent)  # real prompt text was sent
    assert result["labels"]["measured"] is True
    assert result["labels"]["provenance"] == "live"
    assert result["labels"]["spend_source"] == "provider-usage"


# -- Microsoft Entra ID (Azure AD) keyless auth -----------------------------


def test_config_entra_autodetected_without_api_key() -> None:
    # Resource with local/key auth disabled: only endpoint + deployment set.
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://r.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
        }
    )
    assert config.auth_method == "entra"
    assert config.credentialed is True
    # The API key is not a gap under Entra ID auth.
    assert "AZURE_AI_FOUNDRY_API_KEY" not in config.missing()
    status = config.status()
    assert status["auth_method"] == "entra"
    assert status["token_scope"] == "https://cognitiveservices.azure.com/.default"
    assert status["api_key"] == "missing"
    assert status["measured"] is False


def test_config_explicit_entra_prefers_token_over_present_key() -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://r.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "keyABCDWXYZ",
            "AZURE_AI_FOUNDRY_AUTH": "entra",
        }
    )
    assert config.auth_method == "entra"
    assert config.credentialed is True


def test_config_explicit_key_without_key_is_not_credentialed() -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://r.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_AUTH": "key",
        }
    )
    assert config.auth_method == "none"
    assert config.credentialed is False
    assert "AZURE_AI_FOUNDRY_API_KEY" in config.missing()


def test_config_custom_token_scope_is_respected() -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://r.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_TOKEN_SCOPE": "api://custom-scope/.default",
        }
    )
    assert config.resolved_token_scope == "api://custom-scope/.default"
    assert config.status()["token_scope"] == "api://custom-scope/.default"


def test_entra_client_builds_sdk_with_token_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://r.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
        }
    )
    captured = _install_fake_openai(monkeypatch, _canned_response("gpt-4o-mini"))
    client = AzureModelRouterClient(config=config, token_provider=lambda: "tok-abc")
    client._sdk_client()
    assert "azure_ad_token_provider" in captured
    assert "api_key" not in captured
    assert captured["azure_ad_token_provider"]() == "tok-abc"
    assert captured["azure_endpoint"] == "https://r.example/"


def test_key_client_builds_sdk_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://r.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_API_KEY": "keyABCDWXYZ",
        }
    )
    captured = _install_fake_openai(monkeypatch, _canned_response("gpt-4o"))
    client = AzureModelRouterClient(config=config)
    client._sdk_client()
    assert captured["api_key"] == "keyABCDWXYZ"
    assert "azure_ad_token_provider" not in captured


def test_entra_live_call_sends_prompt_and_measures(monkeypatch: pytest.MonkeyPatch) -> None:
    config = FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://r.example/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_AUTH": "entra",
        }
    )
    captured = _install_fake_openai(monkeypatch, _canned_response("gpt-4o-mini"))
    client = AzureModelRouterClient(config=config, token_provider=lambda: "tok-xyz")
    outcome = client.complete({"task_id": "t-0001", "prompt": "Write a slugify() helper."})
    assert outcome.provenance == "live"
    assert outcome.model == "gpt-4o-mini"
    # Keyless: token provider was wired, no api_key ever passed to the SDK.
    assert "azure_ad_token_provider" in captured
    assert "api_key" not in captured


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


# -- dotenv loading: make the documented `.env` workflow actually work -------


def test_load_dotenv_parses_and_respects_precedence(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        'export AZURE_AI_FOUNDRY_ENDPOINT="https://demo.example/"\n'
        "AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router\n"
        "AZURE_AI_FOUNDRY_API_KEY='quoted-secret'\n"
        "not a config line\n",
        encoding="utf-8",
    )
    target: dict[str, str] = {"AZURE_AI_FOUNDRY_MODEL_ROUTER": "preset-wins"}
    applied = load_dotenv_file(env_file, environ=target)

    # comment, blank, and the malformed line are skipped; quotes/export stripped
    assert applied == ["AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_AI_FOUNDRY_API_KEY"]
    assert target["AZURE_AI_FOUNDRY_ENDPOINT"] == "https://demo.example/"
    assert target["AZURE_AI_FOUNDRY_API_KEY"] == "quoted-secret"
    # override=False: a value already present in the environment is never replaced
    assert target["AZURE_AI_FOUNDRY_MODEL_ROUTER"] == "preset-wins"


def test_load_dotenv_missing_file_is_a_noop(tmp_path: Path) -> None:
    target: dict[str, str] = {}
    assert load_dotenv_file(tmp_path / "does-not-exist.env", environ=target) == []
    assert target == {}


def test_cli_foundry_status_loads_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Start from a clean slate so only the .env supplies the config.
    for name in (
        "AZURE_AI_FOUNDRY_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_AI_FOUNDRY_MODEL_ROUTER",
        "AZURE_MODEL_ROUTER_DEPLOYMENT",
        "AZURE_AI_FOUNDRY_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AZURE_AI_FOUNDRY_ENDPOINT=https://loaded.example/\n"
        "AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router\n"
        "AZURE_AI_FOUNDRY_API_KEY=fromDotEnvKEY9\n",
        encoding="utf-8",
    )
    rc = cli.main(["foundry", "status", "--json", "--env-file", str(env_file)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["credentialed"] is True
    assert payload["endpoint"] == "https://loaded.example"
    assert payload["dotenv_loaded"] == 3
    assert "fromDotEnvKEY9" not in json.dumps(payload)
    assert payload["api_key"] == "set (****KEY9)"


def test_cli_foundry_status_keyless_reports_entra(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Keyless tenant: only endpoint + deployment, no API key anywhere.
    for name in (
        "AZURE_AI_FOUNDRY_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_AI_FOUNDRY_MODEL_ROUTER",
        "AZURE_MODEL_ROUTER_DEPLOYMENT",
        "AZURE_AI_FOUNDRY_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AZURE_AI_FOUNDRY_ENDPOINT=https://keyless.example/\n"
        "AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router\n",
        encoding="utf-8",
    )
    # JSON: credentialed via Entra, no API key required.
    assert cli.main(["foundry", "status", "--json", "--env-file", str(env_file)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["credentialed"] is True
    assert payload["auth_method"] == "entra"
    assert payload["api_key"] == "missing"
    assert "AZURE_AI_FOUNDRY_API_KEY" not in payload["missing"]
    # Human-readable: names the Entra path.
    assert cli.main(["foundry", "status", "--env-file", str(env_file)]) == 0
    text = capsys.readouterr().out
    assert "Entra ID" in text
    assert "token scope" in text
