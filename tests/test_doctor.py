"""Tests for the doctor pre-flight (BOLT-03B step 6). Fully offline."""

from __future__ import annotations

import pytest

from router.doctor import (
    FAIL,
    OK,
    UNKNOWN,
    DeploymentEvidence,
    DoctorInputs,
    evaluate_deployment_modes,
    live_routing_mode,
    run_doctor,
    verify_deployment_evidence,
)


def _inputs(**overrides) -> DoctorInputs:
    base = dict(
        run_mode="smoke",
        endpoint="https://aoai-demo.cognitiveservices.azure.com/",
        endpoint_kind="azure_openai",
        deployments=["gpt-4o"],
        arms=[{"name": "cheapest"}],
        workload_path="samples/workloads/validated-smoke.example.jsonl",
        workload_ok=True,
        rate_card_present=True,
        unpriced_direct_arms=(),
        partial_direct_arms=(),
        router_arm_ids=(),
        authorization_ceiling_usd=1.0,
        planned_cells=5,
        base_transport_attempts=1,
        max_transport_attempts=3,
        output_token_ceiling=4096,
        conservative_max_authorized_spend_usd="0.150000",
        prereg_note="smoke wiring-only; preregistration not required",
        prereg_allowed=True,
        output_dir="/tmp/runs",
        output_dir_writable=True,
        retain_raw_outputs=False,
        wiring_only=True,
        deps_present=True,
    )
    base.update(overrides)
    return DoctorInputs(**base)


def _get(report, name):
    return next(c for c in report.checks if c.name == name)


# --- authentication vs authorization are three distinct facts ---------------

def test_token_rbac_deployment_are_separate_fields():
    report = run_doctor(
        _inputs(),
        token_probe=lambda: "tok",
        rbac_probe=lambda: None,
        deployment_probe=lambda: None,
    )
    assert report.token_acquired is True
    assert report.data_plane_rbac_verified is None
    assert report.deployment_config_verified is None


def test_token_acquired_is_not_rbac_proof():
    report = run_doctor(_inputs(), token_probe=lambda: "tok", rbac_probe=lambda: None)
    assert report.token_acquired is True
    # A token does not imply RBAC.
    assert report.data_plane_rbac_verified is None
    assert "not RBAC proof" in _get(report, "token").detail


def test_token_failure_sets_false_and_fails():
    def boom():
        raise RuntimeError("no credential")

    report = run_doctor(_inputs(), token_probe=boom)
    assert report.token_acquired is False
    assert _get(report, "token").status == FAIL


def test_missing_token_probe_is_unknown_not_success():
    report = run_doctor(_inputs(), token_probe=None)
    assert report.token_acquired is False
    assert _get(report, "token").status == UNKNOWN


# --- unknown is never rendered as success -----------------------------------

def test_unknown_never_rendered_as_success():
    report = run_doctor(
        _inputs(), token_probe=lambda: "tok", rbac_probe=lambda: None,
        deployment_probe=lambda: None,
    )
    text = report.to_text()
    assert "data_plane_rbac_verified = unknown" in text
    assert "deployment_config_verified = unknown" in text
    # unknown rows are not marked with the success glyph
    for line in text.splitlines():
        if "rbac:" in line or "deployments:" in line:
            assert not line.startswith("✓")


def test_deployment_unknown_is_unknown_status():
    report = run_doctor(_inputs(), deployment_probe=lambda: None)
    assert report.deployment_config_verified is None
    assert _get(report, "deployments").status == UNKNOWN


def test_deployment_verified_true():
    report = run_doctor(_inputs(), deployment_probe=lambda: True)
    assert report.deployment_config_verified is True
    assert _get(report, "deployments").status == OK


def test_no_deployment_configured_fails():
    report = run_doctor(_inputs(deployments=[]))
    assert _get(report, "deployments").status == FAIL
    assert report.deployment_config_verified is False


# --- RBAC failure must not dead-end -----------------------------------------

def test_rbac_unknown_prints_lookup_first_then_assignment():
    report = run_doctor(_inputs(), rbac_probe=lambda: None)
    check = _get(report, "rbac")
    assert check.status == UNKNOWN
    remediation = check.next_step
    assert remediation is not None
    # read-only lookup appears before the mutating assignment
    show_idx = remediation.index("az cognitiveservices account show")
    assign_idx = remediation.index("az role assignment create")
    assert show_idx < assign_idx


def test_rbac_remediation_uses_placeholders_not_guessed_ids():
    report = run_doctor(_inputs(), rbac_probe=lambda: False)
    remediation = _get(report, "rbac").next_step
    assert "<PRINCIPAL_ID>" in remediation
    assert "<RESOURCE_ID>" in remediation
    # Never emit the real tenant/subscription IDs from the environment memory.
    assert "6d93cc9b" not in remediation
    assert "4b7c60a5" not in remediation


def test_rbac_false_fails_with_remediation():
    report = run_doctor(_inputs(), rbac_probe=lambda: False)
    check = _get(report, "rbac")
    assert check.status == FAIL
    assert report.data_plane_rbac_verified is False
    assert check.next_step is not None


def test_rbac_true_ok():
    report = run_doctor(_inputs(), rbac_probe=lambda: True)
    assert report.data_plane_rbac_verified is True
    assert _get(report, "rbac").status == OK


def test_rbac_probe_exception_is_unknown_not_false():
    def boom():
        raise RuntimeError("read-only lookup unavailable")

    report = run_doctor(_inputs(), rbac_probe=boom)
    assert report.data_plane_rbac_verified is None
    assert _get(report, "rbac").status == UNKNOWN


# --- doctor never sends an inference prompt ---------------------------------

def test_doctor_only_calls_injected_probes():
    calls: list[str] = []
    run_doctor(
        _inputs(),
        token_probe=lambda: (calls.append("token"), "tok")[1],
        rbac_probe=lambda: (calls.append("rbac"), True)[1],
        deployment_probe=lambda: (calls.append("deploy"), True)[1],
    )
    # Exactly the identity/management probes — no inference surface exists.
    assert calls == ["token", "rbac", "deploy"]


# --- pricing coverage -------------------------------------------------------

def test_benchmark_requires_complete_pinned_pricing():
    report = run_doctor(
        _inputs(run_mode="benchmark",
                unpriced_direct_arms=(("premium", "gpt-9-unlisted"),)),
        token_probe=lambda: "tok", rbac_probe=lambda: True,
        deployment_probe=lambda: True,
    )
    check = _get(report, "pricing")
    assert check.status == FAIL
    # The operator has to be able to act on it: name the arm and the model.
    assert "premium" in check.detail and "gpt-9-unlisted" in check.detail


def test_benchmark_pricing_ok_only_when_every_arm_is_direct_and_pinned():
    report = run_doctor(
        _inputs(run_mode="benchmark"),
        token_probe=lambda: "tok", rbac_probe=lambda: True,
        deployment_probe=lambda: True,
    )
    assert _get(report, "pricing").status == OK


def test_router_arm_pricing_coverage_is_unknown_never_ok():
    # Regression: doctor used to print "complete pinned pricing coverage for
    # every arm" whenever a rate-card path was configured -- the coverage flag
    # was aliased to mere presence and nothing was ever looked up. A router arm's
    # backend is chosen per prompt, so coverage cannot be proven in advance; the
    # 03D-3 run then billed a backend absent from the card, withheld its cost and
    # lost that arm's savings claim, after doctor had reported green.
    report = run_doctor(
        _inputs(run_mode="benchmark", router_arm_ids=("router-balanced",)),
        token_probe=lambda: "tok", rbac_probe=lambda: True,
        deployment_probe=lambda: True,
    )
    check = _get(report, "pricing")
    assert check.status == UNKNOWN
    assert "router-balanced" in check.detail
    # unknown must stay actionable: say what an unpriced backend costs them.
    assert check.next_step and "cost_complete=false" in check.next_step
    # ...and it must not block dispatch -- it is a warning, not a gate.
    assert all(c.status != FAIL for c in report.checks)


def test_partially_pinned_direct_rate_is_not_reported_as_complete():
    # A pinned key is necessary but not sufficient: a null cached/reasoning
    # component still fails the cell closed once tokens of that kind appear.
    report = run_doctor(
        _inputs(run_mode="benchmark",
                partial_direct_arms=(("premium", "grok-4-1-fast (cached unpinned)"),)),
        token_probe=lambda: "tok", rbac_probe=lambda: True,
        deployment_probe=lambda: True,
    )
    check = _get(report, "pricing")
    assert check.status == UNKNOWN
    assert "cached unpinned" in check.detail


def test_smoke_ok_with_authorization_ceiling_only():
    report = run_doctor(
        _inputs(run_mode="smoke", rate_card_present=False,
                unpriced_direct_arms=(("premium", "gpt-9-unlisted"),),
                authorization_ceiling_usd=0.5)
    )
    assert _get(report, "pricing").status == OK


def test_smoke_without_pricing_or_ceiling_fails():
    report = run_doctor(
        _inputs(run_mode="smoke", rate_card_present=False,
                unpriced_direct_arms=(("premium", "gpt-9-unlisted"),),
                authorization_ceiling_usd=None)
    )
    assert _get(report, "pricing").status == FAIL


# --- endpoint safety --------------------------------------------------------

def test_non_https_endpoint_fails():
    report = run_doctor(_inputs(endpoint="http://evil.example.com/"))
    assert _get(report, "endpoint").status == FAIL


def test_unrecognized_host_fails():
    report = run_doctor(_inputs(endpoint="https://evil.example.com/"))
    assert _get(report, "endpoint").status == FAIL


def test_recognized_host_ok():
    report = run_doctor(_inputs())
    assert _get(report, "endpoint").status == OK


# --- approval bounds never say "exactly N" ----------------------------------

def test_plan_bounds_show_base_and_max_not_exactly():
    report = run_doctor(_inputs(base_transport_attempts=1, max_transport_attempts=3))
    detail = _get(report, "authorized spend").detail
    assert "up to 3 transport attempts" in detail
    assert "base 1" in detail
    assert "exactly" not in detail.lower()


# --- benchmark fail-closed gate: unknown blocks the paid path ---------------

def test_benchmark_gate_blocks_on_unknown_rbac():
    report = run_doctor(
        _inputs(run_mode="benchmark"),
        token_probe=lambda: "tok", rbac_probe=lambda: None,
        deployment_probe=lambda: True,
    )
    gate = _get(report, "benchmark authorization")
    assert gate.status == FAIL
    assert "data_plane_rbac_verified" in gate.detail
    assert report.ready is False


def test_benchmark_gate_passes_when_all_verified():
    report = run_doctor(
        _inputs(run_mode="benchmark"),
        token_probe=lambda: "tok", rbac_probe=lambda: True,
        deployment_probe=lambda: True,
    )
    assert _get(report, "benchmark authorization").status == OK


def test_smoke_has_no_benchmark_gate():
    report = run_doctor(_inputs(run_mode="smoke"))
    assert not any(c.name == "benchmark authorization" for c in report.checks)


def test_ready_is_false_when_any_check_fails():
    report = run_doctor(_inputs(deployments=[]))
    assert report.ready is False


# --- deployment evidence verification (mode/version/subset + propagation) ----

def _evidence(**over):
    base = dict(
        management_api_version="2024-10-01", retrieved_at="2026-07-01T00:00:00Z",
        payload_hash="abc", etag="v1", mode="router", version="2025-01-01",
        subset=("gpt-4o", "grok"),
    )
    base.update(over)
    return DeploymentEvidence(**base)


def test_deployment_evidence_match():
    ok, note = verify_deployment_evidence(_evidence(), _evidence())
    assert ok is True
    assert "matches" in note


def test_deployment_evidence_mismatch_outside_window_fails():
    ok, note = verify_deployment_evidence(
        _evidence(), _evidence(version="2025-09-09", payload_hash="zzz")
    )
    assert ok is False
    assert "differs" in note


def test_deployment_evidence_mismatch_within_window_waits():
    ok, note = verify_deployment_evidence(
        _evidence(), _evidence(subset=("gpt-4o",), payload_hash="zzz"),
        seconds_since_change=30,
    )
    assert ok is False
    assert "propagation window" in note


def test_deployment_evidence_subset_matters():
    a = _evidence(subset=("gpt-4o", "grok"))
    b = _evidence(subset=("gpt-4o",))
    assert a.matches(b) is False


# --- live routing-mode readback (03D STEP 1) --------------------------------
# The management-plane GET only exposes properties.routing.mode on the newer
# api-version; an ABSENT routing block is the Model Router's default (Balanced).

_ARMS = [
    {"id": "router-cost", "deployment": "model-router-cost",
     "kind": "model_router", "expected": {"routing_mode": "Cost"}},
    {"id": "router-balanced", "deployment": "model-router",
     "kind": "model_router", "expected": {"routing_mode": "Balanced"}},
    {"id": "router-quality", "deployment": "model-router-quality",
     "kind": "model_router", "expected": {"routing_mode": "Quality"}},
    {"id": "direct-premium", "deployment": "gpt-5.6-sol",
     "kind": "direct", "expected": {"name": "gpt-5.6-sol", "version": "2026-07-09"}},
]

_LIVE_OK = {
    "model-router-cost": {"routing": {"mode": "Cost"}},
    "model-router": {},  # absent block => Balanced default
    "model-router-quality": {"routing": {"mode": "Quality"}},
    "gpt-5.6-sol": {"model": {"name": "gpt-5.6-sol", "version": "2026-07-09"}},
}


def test_live_routing_mode_absent_block_is_balanced():
    assert live_routing_mode({}) == "Balanced"
    assert live_routing_mode({"routing": {}}) == "Balanced"
    assert live_routing_mode({"routing": {"mode": "Quality"}}) == "Quality"


def test_evaluate_deployment_modes_all_match():
    ok, lines = evaluate_deployment_modes(_ARMS, _LIVE_OK)
    assert ok is True
    assert len(lines) == 4
    assert all("OK" in line for line in lines)


def test_evaluate_deployment_modes_mode_mismatch_is_false():
    live = {**_LIVE_OK, "model-router-quality": {"routing": {"mode": "Cost"}}}
    ok, lines = evaluate_deployment_modes(_ARMS, live)
    assert ok is False
    assert any("MISMATCH" in line for line in lines)


def test_evaluate_deployment_modes_absent_block_matches_balanced():
    # The balanced arm expects "Balanced" and the live deployment omits routing.
    ok, _ = evaluate_deployment_modes([_ARMS[1]], {"model-router": {}})
    assert ok is True


def test_evaluate_deployment_modes_direct_model_mismatch_is_false():
    live = {**_LIVE_OK,
            "gpt-5.6-sol": {"model": {"name": "gpt-5.6-sol", "version": "2099-01-01"}}}
    ok, lines = evaluate_deployment_modes(_ARMS, live)
    assert ok is False
    assert any("direct-premium" in line and "MISMATCH" in line for line in lines)


def test_evaluate_deployment_modes_unreadable_is_unknown_not_false():
    live = {**_LIVE_OK, "gpt-5.6-sol": None}
    ok, lines = evaluate_deployment_modes(_ARMS, live)
    assert ok is None  # unknown, never silently OK
    assert any("unreadable" in line for line in lines)


def test_evaluate_deployment_modes_missing_deployment_is_unknown():
    # A deployment absent from the live map is unreadable, not a match.
    ok, _ = evaluate_deployment_modes(_ARMS, {})
    assert ok is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
