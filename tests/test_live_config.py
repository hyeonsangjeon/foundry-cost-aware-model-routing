"""BOLT-03A — canonical :class:`ResolvedRunPlan` acceptance tests.

Every test here is network-free: plans are resolved and executed through a
scripted fake :class:`~router.measure.MeasureClient`, so nothing egresses. The
suite pins the §7 acceptance contract — deterministic ``plan_hash``, the
locale/hash boundary, approval binding, and the single-source-of-truth flow from
preview through the sealed manifest and replay.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from router import cli
from router.foundry_live import DEFAULT_API_VERSION
from router.measure import AttemptResult, replay_measure
from router.run_plan import (
    ApprovalError,
    LocalRunConfig,
    PlanError,
    check_approval,
    execute_benchmark,
    resolve_run_plan,
    write_local_config,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "foundry.example.yaml"
SMOKE_WORKLOAD = "samples/workloads/validated-smoke.example.jsonl"


# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #


class FakeClient:
    """Deterministic offline client: fixed usage per attempt, records its calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def attempt(self, *, deployment: str, provider: str, task: dict[str, Any]) -> AttemptResult:
        self.calls.append((deployment, task["task_id"]))
        return AttemptResult(
            http_status=200,
            model=deployment,
            usage={"input": 1000, "cached": 0, "output": 400, "reasoning": 0},
            latency_ms=10.0,
            provenance="live",
        )


def _rate_card(tmp_path: Path, *, version: int = 7) -> Path:
    path = tmp_path / "tenant-rates.yaml"
    path.write_text(
        # `effective_date` is left unquoted on purpose so YAML parses it as a
        # date — exercising the resolver's date→ISO coercion in the plan hash.
        f"version: {version}\n"
        "currency: USD\n"
        "source: acme-tenant\n"
        "effective_date: 2026-08-01\n"
        "pricing_basis: composite\n"
        "models:\n"
        "  model-router: {input: 3.0, cached: 1.5, output: 10.0, reasoning: 10.0}\n"
        "  premium-max: {input: 5.0, cached: 2.5, output: 15.0, reasoning: 15.0}\n"
        "  cheap-floor: {input: 0.2, cached: 0.1, output: 0.5, reasoning: 0.5}\n"
        "default: {input: 1.0, cached: 0.5, output: 2.0, reasoning: 2.0}\n",
        encoding="utf-8",
    )
    return path


def _benchmark_config(
    tmp_path: Path,
    *,
    max_retries: int = 3,
    repetitions: int = 2,
    max_output_tokens: int = 256,
    budget_usd: float = 5.0,
    rate_card: str = "tenant-rates.yaml",
) -> dict[str, Any]:
    """A run-ready *benchmark* config mapping with an explicit Model Router arm."""

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
            {
                "id": "router-cost",
                "kind": "model_router",
                "provider": "openai",
                "requested_model": "model-router",
                "deployment": "model-router",
                "expected": {"format": "router", "name": "cost", "version": "2025-01"},
            },
            {
                "id": "direct-premium",
                "kind": "direct",
                "provider": "openai",
                "requested_model": "premium-max",
                "deployment": "premium-max",
            },
        ],
        "benchmark": {
            "workload": str(ROOT / SMOKE_WORKLOAD),
            "rate_card": rate_card,
            "smoke_authorization_ceiling_usd": None,
            "repetitions": repetitions,
            "max_output_tokens": max_output_tokens,
            "budget_usd": budget_usd,
            "random_seed": 7,
            "estimand": {
                "analysis_unit": "task",
                "repeat_aggregation": "mean",
                "denominator_policy": "all-attempted",
                "failure_policy": "count-as-zero",
                "cost_per_pass_formula": "total_cost / passes",
                "paired_statistic": "wilcoxon",
            },
            "grader": {"kind": "exec-signals", "version": 1},
            "retry": {"max_retries": max_retries},
        },
        "privacy": {"retain_raw_prompts": True, "retain_raw_outputs": True},
        "artifacts": {"local_root": "results/local"},
        "display": {"locale": "en"},
    }


def _resolve(tmp_path: Path, mapping: dict[str, Any], **kwargs: Any):
    _rate_card(tmp_path)
    config = LocalRunConfig.from_mapping(
        mapping, base_dir=tmp_path, source=str(tmp_path / ".foundry.local.yaml")
    )
    return config, resolve_run_plan(config, env={}, **kwargs)


# --------------------------------------------------------------------------- #
# config init — placeholder file, no secret field
# --------------------------------------------------------------------------- #


def test_config_init_writes_placeholder_without_secret(tmp_path: Path) -> None:
    out = write_local_config(tmp_path / ".foundry.local.yaml", template_path=TEMPLATE)
    assert out.is_file()
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["template"] is True
    # No credential key anywhere in the written config.
    flat = json.dumps(data).lower()
    for secret in ("api_key", "access_token", "client_secret", "connection_string", "password"):
        assert f'"{secret}"' not in flat
    # The placeholder is resolvable and reports live_ready=false.
    config = LocalRunConfig.from_mapping(data, base_dir=ROOT)
    plan = resolve_run_plan(config, env={})
    assert plan.live_ready is False
    assert plan.template is True


def test_config_init_refuses_to_clobber(tmp_path: Path) -> None:
    target = tmp_path / ".foundry.local.yaml"
    write_local_config(target, template_path=TEMPLATE)
    with pytest.raises(PlanError, match="already exists"):
        write_local_config(target, template_path=TEMPLATE)
    # --force overwrites.
    assert write_local_config(target, force=True, template_path=TEMPLATE) == target


def test_cli_config_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(ROOT)
    out = tmp_path / "local.yaml"
    assert cli.main(["config", "init", "--output", str(out)]) == 0
    assert "wrote" in capsys.readouterr().out
    assert out.is_file()


def test_committed_template_has_no_secret_field() -> None:
    data = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    # LocalRunConfig runs the credential denylist at parse time.
    LocalRunConfig.from_mapping(data, base_dir=ROOT)  # must not raise


def _v2_rate_card(tmp_path: Path, *, pin_premium: bool = True,
                  premium_cached: str = "2.5") -> None:
    """A minimal schema-v2 card. ``model-router`` is deliberately absent from
    ``rates`` — a router arm's *deployment name* is never a pricing key, which is
    why router coverage cannot be settled by a pre-flight lookup at all."""

    premium = (
        f"  premium-max: {{input: 5.0, output: 15.0, cached: {premium_cached}, "
        "reasoning: 15.0}\n"
    ) if pin_premium else ""
    (tmp_path / "v2-rates.yaml").write_text(
        "schema_version: 2\n"
        "currency: USD\n"
        "unit_basis: per_1m_tokens\n"
        "source: test-fixture\n"
        "effective_date: \"2026-08-01\"\n"
        "router_input_markup: 0.14\n"
        "alias_map:\n"
        "  version: 1\n"
        "  entries: {}\n"
        "rates:\n" + (premium or "  unused-floor: {input: 0.1, output: 0.2}\n"),
        encoding="utf-8",
    )


def test_doctor_pricing_coverage_is_computed_not_assumed(tmp_path: Path) -> None:
    # Regression: DoctorInputs.rate_card_covers_all_arms was assigned
    # `rate_card_present`, so merely configuring a rate-card path made doctor
    # print "complete pinned pricing coverage for every arm" — an assertion
    # nothing had computed. 03D-3 then billed a router backend that was absent
    # from the card, withheld its cost and lost that arm's savings claim, after
    # doctor had reported green on exactly that config.
    from router.cli import _doctor_inputs_from_plan

    _v2_rate_card(tmp_path)
    mapping = _benchmark_config(tmp_path, rate_card="v2-rates.yaml")
    config, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    inputs = _doctor_inputs_from_plan(plan, config, deps_present=True)

    # The direct arm's model IS knowable in advance and IS pinned.
    assert inputs.unpriced_direct_arms == ()
    assert inputs.partial_direct_arms == ()
    # The router arm is reported as unverifiable rather than silently "covered".
    assert inputs.router_arm_ids == ("router-cost",)


def test_doctor_flags_a_direct_arm_missing_from_the_card(tmp_path: Path) -> None:
    from router.cli import _doctor_inputs_from_plan

    _v2_rate_card(tmp_path, pin_premium=False)
    mapping = _benchmark_config(tmp_path, rate_card="v2-rates.yaml")
    config, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    inputs = _doctor_inputs_from_plan(plan, config, deps_present=True)

    assert inputs.unpriced_direct_arms == (("direct-premium", "premium-max"),)


def test_doctor_flags_a_pinned_rate_with_an_unpinned_component(tmp_path: Path) -> None:
    # `cached: null` is an explicit "unsupported" marker that fails the cell
    # closed once cached tokens appear — the hole that voided the first 03D run.
    # A key that merely exists must therefore not be reported as full coverage.
    from router.cli import _doctor_inputs_from_plan

    _v2_rate_card(tmp_path, premium_cached="null")
    mapping = _benchmark_config(tmp_path, rate_card="v2-rates.yaml")
    config, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    inputs = _doctor_inputs_from_plan(plan, config, deps_present=True)

    assert inputs.unpriced_direct_arms == ()
    assert inputs.partial_direct_arms == (("direct-premium", "premium-max (cached unpinned)"),)


def test_run_yaml_rejects_credential_field(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["foundry"]["api_key"] = "sk-should-be-rejected"
    _rate_card(tmp_path)
    with pytest.raises(PlanError, match="credential field"):
        LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)


def test_run_yaml_rejects_url_userinfo(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["foundry"]["azure_openai_endpoint"] = "https://user:pass@acme.example.com/"
    _rate_card(tmp_path)
    # The credential-in-URL denylist fires at parse time, before resolution.
    with pytest.raises(PlanError):
        LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)


# --------------------------------------------------------------------------- #
# benchmark plan — offline, redacted, deterministic hash
# --------------------------------------------------------------------------- #


def test_benchmark_plan_offline_prints_full_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    assert cli.main(["benchmark", "plan", "--config", str(TEMPLATE)]) == 0
    out = capsys.readouterr().out
    assert "plan_hash" in out
    assert "planned cells" in out
    assert "router-smoke" in out
    assert "workload" in out


def test_benchmark_plan_makes_no_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Prove "zero egress": if the plan path opened any socket, this would raise.
    import socket

    def _blocked(*_a: Any, **_k: Any):  # noqa: ANN202 - test guard
        raise AssertionError("benchmark plan attempted a network connection")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    mapping = _benchmark_config(tmp_path)
    _rate_card(tmp_path)
    config_path = tmp_path / ".foundry.local.yaml"
    config_path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    assert cli.main(["benchmark", "plan", "--config", str(config_path)]) == 0
    assert "plan_hash" in capsys.readouterr().out


def test_benchmark_plan_json_carries_hash_and_sources(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    # Clear legacy endpoint env so the template placeholder deterministically
    # resolves to unset (otherwise the documented legacy-env fallback fills it).
    for name in ("AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_OPENAI_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["benchmark", "plan", "--config", str(TEMPLATE), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_hash"].startswith("sha256:")
    assert payload["execution"]["run_mode"] == "smoke"
    assert payload["sources"]["workload"] == "yaml"
    # Placeholder endpoint with no legacy env → unset.
    assert payload["execution"]["endpoint"]["data_plane"] is None


def test_doctor_runs_offline_and_reports_separate_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Zero egress: doctor must never open a socket (and never send a prompt).
    import socket

    def _blocked(*_a: Any, **_k: Any):  # noqa: ANN202 - test guard
        raise AssertionError("doctor attempted a network connection")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    # Deterministic regardless of whether the [foundry] extra is installed:
    # the benchmark gate (not incidental missing deps) is what fails closed here.
    monkeypatch.setattr(cli, "_foundry_extra_present", lambda: True)
    mapping = _benchmark_config(tmp_path)
    mapping["foundry"]["azure_openai_endpoint"] = (
        "https://acme-res.cognitiveservices.azure.com/"
    )
    _rate_card(tmp_path)
    config_path = tmp_path / ".foundry.local.yaml"
    config_path.write_text(yaml.safe_dump(mapping), encoding="utf-8")

    # Benchmark with no verified identity/RBAC/deployment → fail closed (exit 1).
    assert cli.main(["doctor", "--config", str(config_path)]) == 1
    out = capsys.readouterr().out
    # The three facts are reported separately, and unknown is not success.
    assert "token_acquired = false" in out
    assert "data_plane_rbac_verified = unknown" in out
    assert "deployment_config_verified = unknown" in out
    # Benchmark fails closed until those are verified.
    assert "benchmark authorization" in out


def test_doctor_json_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.setattr(cli, "_foundry_extra_present", lambda: True)
    mapping = _benchmark_config(tmp_path)
    mapping["run_mode"] = "smoke"
    mapping["foundry"]["azure_openai_endpoint"] = (
        "https://acme-res.cognitiveservices.azure.com/"
    )
    mapping["benchmark"]["smoke_authorization_ceiling_usd"] = 0.5
    mapping["benchmark"]["budget_usd"] = 5.0
    _rate_card(tmp_path)
    config_path = tmp_path / ".foundry.local.yaml"
    config_path.write_text(yaml.safe_dump(mapping), encoding="utf-8")

    assert cli.main(["doctor", "--config", str(config_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["token_acquired"] is False
    assert payload["data_plane_rbac_verified"] is None
    assert payload["deployment_config_verified"] is None
    # smoke has no benchmark-authorization gate, so a template-free smoke is ready.
    assert not any(c["name"] == "benchmark authorization" for c in payload["checks"])


def test_plan_hash_is_deterministic(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    _, plan_a = _resolve(tmp_path, mapping, require_run_ready=True)
    _, plan_b = _resolve(tmp_path, mapping, require_run_ready=True)
    assert plan_a.plan_hash == plan_b.plan_hash


def test_plan_transport_timeouts_reach_the_live_client(tmp_path: Path) -> None:
    # The plan's transport cutoffs are bound into plan_hash and sealed into the
    # run manifest, so they must also reach the socket. Regression: the live
    # benchmark client was built without `timeouts=`, so it fell back to the
    # TransportTimeouts() defaults (read 90 / overall 120) and an approved
    # timeout change was a silent no-op the manifest still reported as applied.
    from router.cli import _live_measure_client
    from router.foundry_live import FoundryConfig

    mapping = _benchmark_config(tmp_path)
    mapping["benchmark"]["retry"] = {
        "max_retries": 4,
        "connect_timeout_seconds": 10,
        "read_timeout_seconds": 180,
        "write_timeout_seconds": 30,
        "pool_timeout_seconds": 10,
        "overall_timeout_seconds": 240,
    }
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    assert plan.execution["retry"]["read_timeout_seconds"] == 180

    client = _live_measure_client(plan, FoundryConfig())
    timeouts = client.client.timeouts
    assert timeouts is not None, "live client must carry the plan's timeouts"
    assert (timeouts.read, timeouts.overall) == (180.0, 240.0)
    assert (timeouts.connect, timeouts.write, timeouts.pool) == (10.0, 30.0, 10.0)


# --------------------------------------------------------------------------- #
# run_mode → the provider scope-out gate
#
# Same defect class as the transport timeouts above, and as preregistration.blob:
# a field the plan carries, hashes, and gets approved on, which never reached the
# code that acts on it. Here the consequence is worse than a silent no-op — the
# unreached field is the one a *fail-closed* gate branches on, so the gate could
# only ever evaluate a smoke, and its refusal never fired on a benchmark run.
# --------------------------------------------------------------------------- #


def _credentialed_config():
    """A config that passes ``credentialed`` so ``complete`` reaches the gate.

    ``complete`` raises on an uncredentialed config *before* it consults the
    scope-out gate, so a test that used the default config would pass whether or
    not the gate was wired at all.
    """

    from router.foundry_live import FoundryConfig

    return FoundryConfig.from_env(
        {
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://acme-res.example.com/",
            "AZURE_AI_FOUNDRY_MODEL_ROUTER": "model-router",
            "AZURE_AI_FOUNDRY_AUTH": "entra",
        }
    )


class _RecordingClient:
    """Stands in for either SDK surface and records every dispatch it receives."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _usage(self):
        return SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=30,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        )

    def _create(self, **kwargs):  # Azure OpenAI chat/completions surface
        self.calls.append(kwargs)
        return SimpleNamespace(
            model=kwargs.get("model"),
            usage=self._usage(),
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )

    def complete(self, *, model, messages, **kwargs):  # partner inference surface
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return SimpleNamespace(model=model, usage=self._usage())


def test_benchmark_run_mode_reaches_the_provider_scope_out_gate(tmp_path: Path) -> None:
    """benchmark + a scoped-out provider must fail closed, before any dispatch.

    The tripwire for the wiring itself. With ``benchmark_mode`` left at its
    default the call below succeeds and bills a measured cost on the retiring
    azure-ai-inference SDK — which is the exact outcome
    ``assert_provider_benchmark_safe`` exists to make impossible.
    """

    from router.cli import _live_measure_client
    from router.foundry_live import ProviderScopedOutError

    _, plan = _resolve(tmp_path, _benchmark_config(tmp_path), require_run_ready=True)
    assert plan.execution["run_mode"] == "benchmark"

    client = _live_measure_client(plan, _credentialed_config())
    assert client.client.benchmark_mode is True, (
        "the plan's run_mode must reach the client, or the scope-out gate can "
        "only ever see a smoke"
    )

    partner = _RecordingClient()
    client.client.inference_client = partner
    with pytest.raises(ProviderScopedOutError):
        client.client.complete(
            {"task_id": "t", "prompt": "hi"},
            deployment="deepseek-v4-pro",
            provider="foundry",
        )
    assert partner.calls == [], "the gate must refuse before anything is dispatched"


def test_benchmark_run_mode_still_allows_the_openai_surface(tmp_path: Path) -> None:
    """The golden path is untouched — this is what the three sealed runs used.

    Every arm of every sealed 03D run is ``provider: openai``, so wiring the gate
    must not change a single one of their cells. If this test ever fails, the fix
    stopped being a scope-out and became a new restriction on measured runs.
    """

    from router.cli import _live_measure_client

    _, plan = _resolve(tmp_path, _benchmark_config(tmp_path), require_run_ready=True)
    assert [arm["provider"] for arm in plan.execution["arms"]] == ["openai", "openai"]

    client = _live_measure_client(plan, _credentialed_config())
    golden = _RecordingClient()
    client.client.sdk_client = golden

    outcome = client.client.complete(
        {"task_id": "t", "prompt": "hi"}, deployment="model-router", provider="openai"
    )
    assert outcome.provenance == "live"
    assert len(golden.calls) == 1, "the openai surface must dispatch exactly as before"


def test_smoke_run_mode_keeps_the_partner_surface_available(tmp_path: Path) -> None:
    """An opt-in wiring smoke on the partner surface stays allowed, as documented.

    The scope-out is about measured cost claims, not about the SDK being
    unusable. Wiring run_mode must not turn the gate into a blanket ban.
    """

    from router.cli import _live_measure_client

    mapping = _benchmark_config(tmp_path)
    mapping["run_mode"] = "smoke"
    _, plan = _resolve(tmp_path, mapping)
    assert plan.execution["run_mode"] == "smoke"

    client = _live_measure_client(plan, _credentialed_config())
    assert client.client.benchmark_mode is False

    partner = _RecordingClient()
    client.client.inference_client = partner
    outcome = client.client.complete(
        {"task_id": "t", "prompt": "hi"},
        deployment="deepseek-v4-pro",
        provider="foundry",
    )
    assert outcome.provenance == "live"
    assert len(partner.calls) == 1


def test_wiring_run_mode_does_not_move_plan_hash() -> None:
    """Adding a *reader* cannot change ``plan_hash``; this pins that it did not.

    ``plan_hash`` is computed over the whole ``execution`` mapping, and
    ``run_mode`` has always been in it — that is precisely why the field could be
    approved, sealed, and still never reach the socket. So giving it a consumer
    moves nothing, and every sealed run stays replayable against its recorded
    hash. The literal below is the shipped template's hash; if a future change
    adds to the hashed surface instead of merely reading from it, this fails and
    says so rather than quietly invalidating an approval.
    """

    plan = resolve_run_plan(LocalRunConfig.from_yaml(TEMPLATE), env={})
    assert "run_mode" in plan.execution, "run_mode must already be part of the hash"
    assert plan.plan_hash == (
        "sha256:d16947f4716bfa8421722ada9dd49fea5ab24a0241630035f802d1ec81b68569"
    )


def test_router_arm_routing_mode_survives_resolution(tmp_path: Path) -> None:
    # A router arm's approved routing mode is expected evidence: it must reach
    # the resolved plan so the doctor deployment probe can verify it, and it must
    # feed plan_hash so the approved mode is frozen at prereg time.
    mapping = _benchmark_config(tmp_path)
    mapping["arms"][0]["expected"]["routing_mode"] = "Cost"
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    router_arm = next(a for a in plan.execution["arms"] if a["kind"] == "model_router")
    assert router_arm["expected"]["routing_mode"] == "Cost"

    before = plan.plan_hash
    changed_map = _benchmark_config(tmp_path)
    changed_map["arms"][0]["expected"]["routing_mode"] = "Quality"
    _, changed = _resolve(tmp_path, changed_map, require_run_ready=True)
    assert changed.plan_hash != before


def test_direct_arm_has_no_routing_mode_key(tmp_path: Path) -> None:
    # Direct arms have no routing mode; the key must not be synthesised.
    mapping = _benchmark_config(tmp_path)
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    direct_arm = next(a for a in plan.execution["arms"] if a["kind"] == "direct")
    assert "routing_mode" not in (direct_arm.get("expected") or {})


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["benchmark"].__setitem__("max_output_tokens", 512),
        lambda m: m["benchmark"].__setitem__("budget_usd", 9.0),
        lambda m: m["benchmark"].__setitem__("repetitions", 3),
        lambda m: m["benchmark"]["retry"].__setitem__("max_retries", 5),
        # The control for the sources work: the *value* of a cutoff is inside the
        # hash even though the record of where it came from is not.
        lambda m: m["benchmark"]["retry"].__setitem__("read_timeout_seconds", 180),
        lambda m: m["benchmark"]["retry"].__setitem__("overall_timeout_seconds", 240),
        lambda m: m["arms"][0].__setitem__("deployment", "model-router-v2"),
        lambda m: m["foundry"].__setitem__("api_version", "2025-01-01"),
        lambda m: m["benchmark"].__setitem__("random_seed", 999),
    ],
)
def test_plan_hash_changes_on_execution_field(tmp_path: Path, mutate: Any) -> None:
    base_map = _benchmark_config(tmp_path)
    _, base = _resolve(tmp_path, base_map, require_run_ready=True)
    mutated = _benchmark_config(tmp_path)
    mutate(mutated)
    _, changed = _resolve(tmp_path, mutated, require_run_ready=True)
    assert changed.plan_hash != base.plan_hash


def test_plan_hash_changes_when_rate_card_changes(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    _rate_card(tmp_path, version=7)
    config = LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)
    before = resolve_run_plan(config, env={}, require_run_ready=True).plan_hash
    _rate_card(tmp_path, version=8)  # same path, different bytes → different fingerprint
    after = resolve_run_plan(config, env={}, require_run_ready=True).plan_hash
    assert before != after


# --------------------------------------------------------------------------- #
# Locale is presentation-only — reserved, excluded from the hash
# --------------------------------------------------------------------------- #


def test_locale_change_does_not_change_plan_hash(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    _rate_card(tmp_path)
    config = LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)
    en = resolve_run_plan(config, env={}, cli_locale="en", require_run_ready=True)
    ko = resolve_run_plan(config, env={}, cli_locale="ko", require_run_ready=True)
    assert en.plan_hash == ko.plan_hash
    assert en.locale == "en"
    assert ko.locale == "ko"


def test_locale_precedence_cli_over_env_over_yaml(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)  # display.locale: en
    _rate_card(tmp_path)
    config = LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)
    # env beats YAML
    env_plan = resolve_run_plan(config, env={"COST_ROUTER_LOCALE": "ko"}, require_run_ready=True)
    assert env_plan.locale == "ko"
    assert env_plan.presentation["locale_source"] == "env"
    # CLI beats env
    cli_plan = resolve_run_plan(
        config, env={"COST_ROUTER_LOCALE": "ko"}, cli_locale="en", require_run_ready=True
    )
    assert cli_plan.locale == "en"
    assert cli_plan.presentation["locale_source"] == "cli"


def test_unsupported_locale_rejected(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    _rate_card(tmp_path)
    config = LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)
    with pytest.raises(PlanError, match="not supported"):
        resolve_run_plan(config, env={}, cli_locale="fr", require_run_ready=True)


def test_cli_reserves_locale_option_everywhere() -> None:
    parser = cli.build_parser()
    for argv in (
        ["benchmark", "plan", "--config", "x", "--locale", "ko"],
        ["dashboard", "--locale", "en"],
        ["serve", "--locale", "ko"],
    ):
        args = parser.parse_args(argv)
        assert args.locale in ("en", "ko")


# --------------------------------------------------------------------------- #
# Single source of truth: preview = approval = run = manifest = replay
# --------------------------------------------------------------------------- #


def test_hash_flows_identically_through_run_manifest_and_replay(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    config, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    result = execute_benchmark(
        config, plan, client=FakeClient(), run_dir=tmp_path / "run", exp_id="benchmark",
        now=datetime(2026, 8, 5, tzinfo=UTC), sleeper=lambda _s: None,
        clock=lambda: "2026-08-05T00:00:00Z",
    )
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["plan_hash"] == plan.plan_hash
    replay = replay_measure(result.run_dir)
    assert replay.plan_hash == plan.plan_hash
    assert replay.ok is True
    # Approval binds to the same hash the preview printed.
    check_approval(plan, plan.plan_hash)  # must not raise


def test_stale_or_mismatched_approval_is_rejected(tmp_path: Path) -> None:
    _, plan = _resolve(tmp_path, _benchmark_config(tmp_path), require_run_ready=True)
    bad_hash = "sha256:" + "0" * 64
    with pytest.raises(ApprovalError):
        check_approval(plan, bad_hash)
    with pytest.raises(ApprovalError):
        check_approval(plan, None)
    # The exact hash (bare or prefixed) is accepted.
    check_approval(plan, plan.plan_hash)
    check_approval(plan, plan.plan_hash.split(":", 1)[1])


def test_cli_benchmark_run_rejects_bad_approval_before_dispatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = _benchmark_config(tmp_path)
    _rate_card(tmp_path)
    config_path = tmp_path / ".foundry.local.yaml"
    config_path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    # A live run with a wrong approval is rejected (exit 1) before any dispatch —
    # no credentials are ever consulted.
    code = cli.main(
        ["benchmark", "run", "--config", str(config_path), "--live",
         "--approve-plan", "sha256:deadbeef", "--env-file", str(tmp_path / "absent.env")]
    )
    assert code == 1
    assert "approval rejected" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Custom fleet + tenant rate card appear identically everywhere
# --------------------------------------------------------------------------- #


def test_custom_arms_and_rate_card_appear_identically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["arms"].append(
        {"id": "direct-cheap", "kind": "direct", "provider": "openai",
         "requested_model": "cheap-floor", "deployment": "cheap-floor"}
    )
    config, plan = _resolve(tmp_path, mapping, require_run_ready=True)

    arm_deployments = {arm["deployment"] for arm in plan.arms}
    assert arm_deployments == {"model-router", "premium-max", "cheap-floor"}

    # Preview text lists every arm.
    cli._print_plan(plan)
    preview = capsys.readouterr().out
    for deployment in arm_deployments:
        assert deployment in preview

    # Fake calls + sealed manifest carry the identical arms and rate-card fingerprint.
    client = FakeClient()
    result = execute_benchmark(
        config, plan, client=client, run_dir=tmp_path / "run", exp_id="benchmark",
        now=datetime(2026, 8, 5, tzinfo=UTC), sleeper=lambda _s: None,
        clock=lambda: "2026-08-05T00:00:00Z",
    )
    called = {deployment for deployment, _task in client.calls}
    assert called == arm_deployments
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {c["deployment"] for c in manifest["candidates"]} == arm_deployments
    assert manifest["plan_hash"] == plan.plan_hash
    # The tenant rate card the plan pinned is the one the run priced with.
    assert plan.execution["pricing"]["fingerprint"].startswith("sha256:")


# --------------------------------------------------------------------------- #
# Approval view: planned cells + base/max transport attempts (never "exactly N")
# --------------------------------------------------------------------------- #


def test_approval_view_shows_cells_and_attempt_band(tmp_path: Path) -> None:
    # 3 tasks × 2 repetitions × 2 arms = 12 planned cells; 3 retries → base 1, max 4.
    _, plan = _resolve(tmp_path, _benchmark_config(tmp_path, max_retries=3, repetitions=2),
                       require_run_ready=True)
    view = plan.approval_view()
    assert view["planned_cells"] == 3 * 2 * 2
    assert view["base_transport_attempts"] == 1
    assert view["max_transport_attempts"] == 4


def test_preview_never_labels_retries_as_exact_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    cli.main(["benchmark", "plan", "--config", str(TEMPLATE)])
    out = capsys.readouterr().out
    assert "base 1, max 1" in out
    assert "not an exact call count" in out


# --------------------------------------------------------------------------- #
# Model Router arm is explicit and can never be dropped
# --------------------------------------------------------------------------- #


def test_model_router_arm_is_explicit_and_never_dropped(tmp_path: Path) -> None:
    # Even though only 'direct' arms could form an ensemble, the model_router arm
    # is resolved from the explicit arms list and dispatched as its own candidate.
    _, plan = _resolve(tmp_path, _benchmark_config(tmp_path), require_run_ready=True)
    candidate_deployments = [c.deployment for c in plan.candidates()]
    assert "model-router" in candidate_deployments
    router_arms = [a for a in plan.arms if a["kind"] == "model_router"]
    assert len(router_arms) == 1


# --------------------------------------------------------------------------- #
# Authorization basis + schema rules
# --------------------------------------------------------------------------- #


def test_smoke_ceiling_only_basis(tmp_path: Path) -> None:
    config = LocalRunConfig.from_mapping(
        yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")), base_dir=ROOT
    )
    plan = resolve_run_plan(config, env={})
    assert plan.authorization_basis == "ceiling_only"
    assert plan.execution["pricing"]["rate_card_path"] is None


def test_smoke_rate_card_with_ceiling_basis(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["run_mode"] = "smoke"
    mapping["benchmark"]["smoke_authorization_ceiling_usd"] = 0.10
    mapping["benchmark"]["budget_usd"] = 0.10
    _, plan = _resolve(tmp_path, mapping)
    assert plan.authorization_basis == "rate_card_with_ceiling"


def test_benchmark_mode_requires_rate_card_and_null_ceiling(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["benchmark"]["rate_card"] = None
    with pytest.raises(PlanError, match="benchmark mode requires a pinned rate_card"):
        _resolve(tmp_path, mapping)
    mapping = _benchmark_config(tmp_path)
    mapping["benchmark"]["smoke_authorization_ceiling_usd"] = 0.05
    with pytest.raises(PlanError, match="smoke_authorization_ceiling_usd: null"):
        _resolve(tmp_path, mapping)


def test_run_ready_rejects_template_and_placeholder(tmp_path: Path) -> None:
    config = LocalRunConfig.from_mapping(
        yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")), base_dir=ROOT
    )
    with pytest.raises(PlanError, match="template"):
        resolve_run_plan(config, env={}, require_run_ready=True)


def test_http_endpoint_rejected(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["foundry"]["azure_openai_endpoint"] = "http://acme.example.com/"
    _rate_card(tmp_path)
    config = LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)
    with pytest.raises(PlanError, match="http"):
        resolve_run_plan(config, env={})


def test_duplicate_arm_id_rejected(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["arms"][1]["id"] = "router-cost"
    _rate_card(tmp_path)
    config = LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)
    with pytest.raises(PlanError, match="duplicate arm id"):
        resolve_run_plan(config, env={})


def test_missing_workload_rejected(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["benchmark"]["workload"] = "does-not-exist.jsonl"
    _rate_card(tmp_path)
    config = LocalRunConfig.from_mapping(mapping, base_dir=tmp_path)
    with pytest.raises(PlanError, match="workload not found"):
        resolve_run_plan(config, env={})


def test_relative_paths_resolve_from_config_dir(tmp_path: Path) -> None:
    # Workload + rate card referenced by config-relative names resolve against the
    # config's directory, not the caller's cwd.
    (tmp_path / "wl.jsonl").write_text(
        '{"task_id": "a", "user_prompt": "hi", '
        '"validation": {"type": "contains", "value": "x"}}\n',
        encoding="utf-8",
    )
    _rate_card(tmp_path)
    mapping = _benchmark_config(tmp_path)
    mapping["benchmark"]["workload"] = "wl.jsonl"
    config = LocalRunConfig.from_mapping(
        mapping, base_dir=tmp_path, source=str(tmp_path / ".foundry.local.yaml")
    )
    plan = resolve_run_plan(config, env={}, require_run_ready=True)
    assert plan.workload_path == "wl.jsonl"
    assert plan.planned_cells == 1 * 2 * 2


# --------------------------------------------------------------------------- #
# Legacy env/flag paths emit a documented deprecation warning
# --------------------------------------------------------------------------- #


def test_legacy_paths_emit_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    assert cli.main(["foundry", "live"]) == 0
    err = capsys.readouterr().err
    assert "deprecated by BOLT-03A" in err
    assert "benchmark plan" in err


def test_measure_run_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    # dry-run (no --live) exits 2 with estimates; the deprecation note is on stderr.
    cli.main(["measure", "run", "curated"])
    assert "deprecated by BOLT-03A" in capsys.readouterr().err


def test_endpoint_is_redacted_to_host_only(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["foundry"]["azure_openai_endpoint"] = (
        "https://acme-res.example.com/openai/deployments/model-router"
    )
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    assert plan.execution["endpoint"]["data_plane"] == "https://acme-res.example.com"


# --------------------------------------------------------------------------- #
# Transport cutoffs — provenance is recorded, and recording it is hash-neutral
# --------------------------------------------------------------------------- #


def test_retry_timeouts_default_to_the_committed_constant(tmp_path: Path) -> None:
    from router.foundry_live import COMMITTED_TRANSPORT_DEFAULTS

    mapping = _benchmark_config(tmp_path)  # retry: {max_retries: N} only
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    for key, committed in COMMITTED_TRANSPORT_DEFAULTS.items():
        assert plan.execution["retry"][key] == committed
        assert plan.sources[f"retry.{key}"] == "default"


def test_retry_timeout_sources_distinguish_yaml_from_default(tmp_path: Path) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["benchmark"]["retry"]["read_timeout_seconds"] = 180
    mapping["benchmark"]["retry"]["overall_timeout_seconds"] = 240
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    assert plan.sources["retry.read_timeout_seconds"] == "yaml"
    assert plan.sources["retry.overall_timeout_seconds"] == "yaml"
    # Untouched cutoffs keep saying "default", so the approval screen can name
    # only the knobs the operator actually moved.
    assert plan.sources["retry.connect_timeout_seconds"] == "default"
    assert plan.sources["retry.write_timeout_seconds"] == "default"
    assert plan.sources["retry.pool_timeout_seconds"] == "default"


def test_recording_timeout_sources_does_not_move_plan_hash(tmp_path: Path) -> None:
    """``sources`` is a sibling of ``execution``, never a member of it.

    Spelling the committed defaults out in the YAML changes where every cutoff
    came from — ``default`` becomes ``yaml`` for all five — while leaving the
    resolved values identical. The hash must not notice, or this display-only
    change would invalidate the approvals of the three sealed runs.
    """

    implicit_map = _benchmark_config(tmp_path)
    explicit_map = _benchmark_config(tmp_path)
    explicit_map["benchmark"]["retry"].update(
        {
            "connect_timeout_seconds": 10,
            "read_timeout_seconds": 90,
            "write_timeout_seconds": 30,
            "pool_timeout_seconds": 10,
            "overall_timeout_seconds": 120,
        }
    )
    _, implicit = _resolve(tmp_path, implicit_map, require_run_ready=True)
    _, explicit = _resolve(tmp_path, explicit_map, require_run_ready=True)

    assert implicit.sources["retry.read_timeout_seconds"] == "default"
    assert explicit.sources["retry.read_timeout_seconds"] == "yaml"
    assert implicit.execution["retry"] == explicit.execution["retry"]
    assert implicit.plan_hash == explicit.plan_hash

    # And no `sources` key leaked into the hashed mapping.
    assert "sources" not in implicit.execution
    payload = json.dumps(implicit.execution, sort_keys=True)
    assert "retry.read_timeout_seconds" not in payload


def test_sealed_run_plan_hashes_are_unchanged_by_this_release() -> None:
    """The three paid runs' approvals must still resolve to the same digest.

    ``plan_hash`` is what an approval binds to; if it moved, every published
    ``plan_hash sha256:…`` on the lab-notebook pages would stop matching its
    manifest. These are the values sealed in the run manifests.
    """

    local_config = ROOT / ".foundry.local.yaml"
    if not local_config.is_file():  # pragma: no cover - operator-only file
        pytest.skip("operator's gitignored run config is not present")
    plan = resolve_run_plan(
        LocalRunConfig.from_yaml(local_config), env={}, require_run_ready=False
    )
    sealed = json.loads(
        (ROOT / "results/local/03d/run/20260814T141510Z/manifest.json").read_text(
            encoding="utf-8"
        )
    )["plan_hash"]
    assert plan.plan_hash == sealed


# --------------------------------------------------------------------------- #
# Approval view — the plan's cutoffs are readable before the spend
# --------------------------------------------------------------------------- #


def test_transport_cutoff_summary_always_labels_overall_not_enforced(
    tmp_path: Path,
) -> None:
    """The label is the whole point of printing ``overall`` at all.

    ``TransportTimeouts.to_httpx`` builds the live client from
    connect/read/write/pool only and no runner-side deadline exists, so an
    unlabelled ``overall 120s`` on an approval screen would be a fresh false
    claim — exactly the class of defect this surface is meant to close.
    """

    mapping = _benchmark_config(tmp_path)
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    summary = cli._transport_cutoff_summary(plan)
    assert "read 90s" in summary
    assert "overall 120s" in summary
    assert "NOT ENFORCED" in summary


def test_approval_view_prints_committed_defaults_on_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = _benchmark_config(tmp_path)
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    cli._print_approval_view(plan)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "transport cutoffs" in ln]
    assert len(lines) == 1
    assert "read 90s, overall 120s" in lines[0]
    assert "NOT ENFORCED" in lines[0]
    assert "committed default" in lines[0]


def test_approval_view_spells_out_a_drift_and_names_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = _benchmark_config(tmp_path)
    mapping["benchmark"]["retry"]["read_timeout_seconds"] = 180
    mapping["benchmark"]["retry"]["overall_timeout_seconds"] = 240
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    cli._print_approval_view(plan)
    out = capsys.readouterr().out
    assert "read 180s, overall 240s" in out
    assert "NOT ENFORCED" in out
    assert "read 90s → 180s" in out and "overall 120s → 240s" in out
    # The operator must be able to see *which file* moved them.
    assert str(tmp_path / ".foundry.local.yaml") in out
    assert "a fresh clone does not inherit these" in out
    # Cutoffs that did not move are not listed as drift.
    assert "connect 10s →" not in out


def test_approval_view_shows_endpoint_modes_and_their_origin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = _benchmark_config(tmp_path)  # foundry.api_version / auth are pinned in YAML
    _, plan = _resolve(tmp_path, mapping, require_run_ready=True)
    cli._print_approval_view(plan)
    out = capsys.readouterr().out
    assert "api_version 2024-10-21 (run config)" in out
    assert "auth entra (run config)" in out
    assert "[display only]" in out

    del mapping["foundry"]["api_version"]
    del mapping["foundry"]["auth"]
    _, fallback = _resolve(tmp_path, mapping, require_run_ready=True)
    cli._print_approval_view(fallback)
    out = capsys.readouterr().out
    assert f"api_version {DEFAULT_API_VERSION} (committed default)" in out
    assert "auth entra (committed default)" in out
