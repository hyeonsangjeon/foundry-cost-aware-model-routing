"""Tests for the config-driven fleet registry and its wiring.

Covers three seams, all network-free and cost-free:

* :mod:`router.fleet` — the registry (load / validate / slate / select / save,
  and the ``resolve`` precedence explicit > env > bundled > default);
* the server ``/fleet`` + ``/fleet/run`` endpoints (recorded relabel, bad-role
  rejection);
* the ``cost-router models`` CLI group and ``foundry arena --fleet`` plumbing,
  plus the ``serve`` port-fallback helper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from router import cli
from router.fleet import (
    BUNDLED_FLEET_PATH,
    FleetModel,
    FleetRegistry,
    save_fleet,
)
from router.server import RouterService, _bind_with_fallback, make_server

ROOT = Path(__file__).resolve().parents[1]
BUNDLED_FLEET = ROOT / "samples" / "fleet" / "foundry-5series.fleet.yaml"
SINGLE_FLEET = ROOT / "samples" / "fleet" / "single-deployment.example.yaml"


# --------------------------------------------------------------------------- #
# Registry unit tests
# --------------------------------------------------------------------------- #


def test_default_registry_is_valid_and_maps_roles_to_deployments() -> None:
    reg = FleetRegistry.default()
    assert reg.validation_errors() == []
    slate = reg.slate()
    assert slate.router == "model-router"
    assert slate.cheapest == "gpt-5.4-nano"
    assert slate.premium == "gpt-5.4"
    assert slate.ensemble == ("gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.4")


def test_bundled_sample_matches_in_code_default() -> None:
    from_file = FleetRegistry.from_yaml(BUNDLED_FLEET)
    default = FleetRegistry.default()
    assert from_file.role_assignments() == default.role_assignments()
    assert from_file.model_names() == default.model_names()
    # source records where it came from, not "bundled default"
    assert from_file.source == str(BUNDLED_FLEET)


def test_deployment_decoupled_from_logical_name() -> None:
    reg = FleetRegistry.from_mapping(
        {
            "models": [{"name": "gpt-5.4", "deployment": "prod-gpt54-eastus"}],
            "roles": {
                "router": "gpt-5.4",
                "cheapest": "gpt-5.4",
                "premium": "gpt-5.4",
                "ensemble": ["gpt-5.4"],
            },
        }
    )
    assert reg.deployment_for("gpt-5.4") == "prod-gpt54-eastus"
    assert reg.slate().router == "prod-gpt54-eastus"


def test_from_mapping_accepts_name_to_deployment_map() -> None:
    reg = FleetRegistry.from_mapping(
        {
            "models": {"cheap": "dep-cheap", "big": "dep-big"},
            "roles": {
                "router": "big",
                "cheapest": "cheap",
                "premium": "big",
                "ensemble": "cheap, big",
            },
        }
    )
    assert set(reg.model_names()) == {"cheap", "big"}
    assert reg.ensemble == ("cheap", "big")  # comma string is split
    assert reg.deployment_for("cheap") == "dep-cheap"


def test_single_deployment_sample_ties_every_arm() -> None:
    reg = FleetRegistry.from_yaml(SINGLE_FLEET)
    assert reg.validation_errors() == []
    slate = reg.slate()
    assert slate.router == slate.cheapest == slate.premium == "gpt-4o"
    assert slate.deployments() == ("gpt-4o",)


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda r: r.__class__(models=(), router="", cheapest="", premium="", ensemble=()),
         "catalog is empty"),
    ],
)
def test_validation_errors_surface(mutate, needle) -> None:
    reg = mutate(FleetRegistry.default())
    errors = reg.validation_errors()
    assert any(needle in e for e in errors)


def test_unknown_role_model_is_invalid() -> None:
    reg = FleetRegistry.default()
    bad = FleetRegistry(
        models=reg.models,
        router="does-not-exist",
        cheapest=reg.cheapest,
        premium=reg.premium,
        ensemble=reg.ensemble,
    )
    errors = bad.validation_errors()
    assert any("router" in e and "does-not-exist" in e for e in errors)
    with pytest.raises(ValueError, match="invalid fleet"):
        bad.slate()


def test_empty_ensemble_is_invalid() -> None:
    reg = FleetRegistry.default()
    bad = FleetRegistry(
        models=reg.models,
        router=reg.router,
        cheapest=reg.cheapest,
        premium=reg.premium,
        ensemble=(),
    )
    assert any("ensemble" in e for e in bad.validation_errors())


def test_duplicate_names_are_invalid() -> None:
    dupe = FleetModel("x", "x")
    reg = FleetRegistry(
        models=(dupe, dupe),
        router="x",
        cheapest="x",
        premium="x",
        ensemble=("x",),
    )
    assert any("duplicate" in e for e in reg.validation_errors())


def test_with_roles_returns_new_validated_registry() -> None:
    reg = FleetRegistry.default()
    changed = reg.with_roles(premium="gpt-5.4-mini", ensemble=["gpt-5.4-nano", "gpt-5.4-mini"])
    assert changed.premium == "gpt-5.4-mini"
    assert changed.ensemble == ("gpt-5.4-nano", "gpt-5.4-mini")
    # original is untouched (immutability)
    assert reg.premium == "gpt-5.4"
    with pytest.raises(ValueError):
        reg.with_roles(premium="nope")


def test_roles_for_and_catalog_view() -> None:
    reg = FleetRegistry.default()
    assert "cheapest" in reg.roles_for("gpt-5.4-nano")
    assert "ensemble / fan-out" in reg.roles_for("gpt-5.4-nano")
    view = reg.catalog_view()
    router_row = next(r for r in view if r["name"] == "model-router")
    assert router_row["roles"] == ["router (main)"]


def test_get_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        FleetRegistry.default().get("ghost")


# --------------------------------------------------------------------------- #
# resolve() precedence
# --------------------------------------------------------------------------- #


def test_resolve_explicit_path_wins(tmp_path: Path) -> None:
    reg = FleetRegistry.resolve(SINGLE_FLEET, env={"FOUNDRY_FLEET_PATH": str(BUNDLED_FLEET)})
    assert reg.model_names() == ("gpt-4o",)  # explicit beat the env var


def test_resolve_env_var_used_when_no_explicit_path() -> None:
    reg = FleetRegistry.resolve(None, env={"FOUNDRY_FLEET_PATH": str(SINGLE_FLEET)})
    assert reg.model_names() == ("gpt-4o",)


def test_resolve_bundled_when_no_path_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    reg = FleetRegistry.resolve(None, env={})
    # bundled sample resolves relative to cwd (repo root)
    assert Path(reg.source) == BUNDLED_FLEET_PATH
    assert "model-router" in reg.model_names()


def test_resolve_default_when_bundled_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no samples/ here
    reg = FleetRegistry.resolve(None, env={})
    assert reg.source == "bundled default"
    assert reg.model_names() == FleetRegistry.default().model_names()


def test_resolve_missing_explicit_path_raises(tmp_path: Path) -> None:
    with pytest.raises((OSError, ValueError)):
        FleetRegistry.resolve(tmp_path / "nope.yaml")


# --------------------------------------------------------------------------- #
# save / roundtrip
# --------------------------------------------------------------------------- #


def test_save_fleet_roundtrips(tmp_path: Path) -> None:
    reg = FleetRegistry.default().with_roles(premium="gpt-5.4-mini")
    out = save_fleet(reg, tmp_path / "picked.local.yaml")
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# cost-router fleet")  # header preserved
    reloaded = FleetRegistry.from_yaml(out)
    assert reloaded.role_assignments() == reg.role_assignments()
    assert reloaded.model_names() == reg.model_names()


def test_save_fleet_refuses_invalid(tmp_path: Path) -> None:
    reg = FleetRegistry.default()
    bad = FleetRegistry(
        models=reg.models, router="", cheapest="", premium="", ensemble=()
    )
    with pytest.raises(ValueError):
        save_fleet(bad, tmp_path / "bad.yaml")


# --------------------------------------------------------------------------- #
# Server: /fleet and /fleet/run
# --------------------------------------------------------------------------- #


@pytest.fixture()
def service() -> RouterService:
    return RouterService()


def test_fleet_view_endpoint(service: RouterService) -> None:
    resp = service.dispatch("GET", "/fleet")
    assert resp.status == 200
    body = resp.payload
    assert isinstance(body["models"], list) and body["models"]
    assert set(body["roles"]) == {"router", "cheapest", "premium", "ensemble"}
    assert "credentialed" in body
    assert body["recorded_available"] is True
    # each catalog row carries its role annotations
    assert all("roles" in row for row in body["models"])


def _post(service: RouterService, path: str, payload: dict) -> tuple[int, dict]:
    resp = service.dispatch("POST", path, json.dumps(payload).encode("utf-8"))
    return resp.status, resp.payload


def test_fleet_run_recorded_relabels_measured_false(service: RouterService) -> None:
    status, body = _post(service, "/fleet/run", {})
    assert status == 200
    assert body["mode"] == "recorded"
    labels = body["report"]["labels"]
    # the underlying snapshot is a real measurement; the web replay must relabel
    assert labels["measured"] is False
    assert labels["provenance"] == "recorded"
    assert "arm_totals" in body["report"]
    # command to measure the selection live, two honest lines
    assert "models select" in body["live_command"]
    assert "foundry arena" in body["live_command"] and "--live" in body["live_command"]
    assert "measured=true" in body["note"]


def test_fleet_run_applies_role_override(service: RouterService) -> None:
    status, body = _post(
        service,
        "/fleet/run",
        {"roles": {"premium": "gpt-5.4-mini", "ensemble": ["gpt-5.4-nano", "gpt-5.4-mini"]}},
    )
    assert status == 200
    assert body["slate"]["premium"] == "gpt-5.4-mini"
    assert body["slate"]["ensemble"] == ["gpt-5.4-nano", "gpt-5.4-mini"]
    assert "--premium gpt-5.4-mini" in body["live_command"]


def test_fleet_run_rejects_unknown_model(service: RouterService) -> None:
    status, body = _post(service, "/fleet/run", {"roles": {"premium": "ghost"}})
    assert status == 400
    assert "ghost" in body["error"]


def test_fleet_run_rejects_non_object_roles(service: RouterService) -> None:
    status, body = _post(service, "/fleet/run", {"roles": ["not", "an", "object"]})
    assert status == 400
    assert "roles" in body["error"]


def test_dashboard_html_carries_fleet_panel(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    assert 'id="fleetPanel"' in html
    assert "function loadFleet" in html
    assert "/fleet/run" in html


# --------------------------------------------------------------------------- #
# CLI: models list / show / select, and arena --fleet
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_models_list_text(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["models", "list"]) == 0
    out = capsys.readouterr().out
    assert "model-router" in out
    assert "current slate" in out
    assert "router (main)" in out


def test_models_list_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["models", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {m["name"] for m in payload["models"]} >= {"gpt-5.4", "model-router"}
    assert set(payload["roles"]) == {"router", "cheapest", "premium", "ensemble"}
    assert "credentialed" in payload


def test_models_show_json_valid(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["models", "show", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["slate"]["cheapest"] == "gpt-5.4-nano"


def test_models_select_flags_persist_and_reload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "sel.local.yaml"
    code = cli.main(
        [
            "models",
            "select",
            "--premium",
            "gpt-5.4-mini",
            "--ensemble",
            "gpt-5.4-nano,gpt-5.4-mini",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert out.is_file()
    text = capsys.readouterr().out
    assert "saved fleet" in text
    # reload via --fleet and confirm the choice stuck
    assert cli.main(["models", "show", "--fleet", str(out), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["slate"]["premium"] == "gpt-5.4-mini"


def test_models_select_unknown_model_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["models", "select", "--premium", "ghost", "--out", str(tmp_path / "x.yaml")]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "ghost" in out
    assert "available models" in out


def test_models_select_non_interactive_keeps_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "keep.local.yaml"
    assert cli.main(["models", "select", "--non-interactive", "--out", str(out)]) == 0
    reloaded = FleetRegistry.from_yaml(out)
    assert reloaded.role_assignments() == FleetRegistry.default().role_assignments()


def test_models_no_subcommand_lists(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["models"]) == 0
    assert "current slate" in capsys.readouterr().out


def test_arena_fleet_not_live_prints_resolved_fleet(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(["foundry", "arena", "--fleet", str(BUNDLED_FLEET)])
    assert code == 2  # not-live: instructs to re-run with --live
    out = capsys.readouterr().out
    assert "router=model-router" in out
    assert "premium=gpt-5.4" in out


# --------------------------------------------------------------------------- #
# serve: graceful port fallback
# --------------------------------------------------------------------------- #


def test_bind_with_fallback_skips_busy_port() -> None:
    service = RouterService()
    first = make_server("127.0.0.1", 0, service=service)  # OS-assigned free port
    busy = first.server_address[1]
    try:
        # asking for the busy port yields a server on a nearby free port
        second = _bind_with_fallback("127.0.0.1", busy, service)
        assert second is not None
        try:
            assert second.server_address[1] != busy
        finally:
            second.server_close()
    finally:
        first.server_close()
