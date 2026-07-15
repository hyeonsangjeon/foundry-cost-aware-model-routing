"""Tests for runtime policy injection precedence and service/CLI wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from router.pipeline import POLICY_ENV_VAR, load_policy, resolve_policy_path
from router.server import RouterService

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "src" / "policy" / "seed_policy.yaml"
CANDIDATE = ROOT / "samples" / "policy" / "candidate.example.yaml"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    monkeypatch.chdir(ROOT)


def test_default_when_no_arg_or_env() -> None:
    assert resolve_policy_path(None) is None
    assert load_policy().version == 1


def test_env_var_used_when_no_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(POLICY_ENV_VAR, str(CANDIDATE))
    assert resolve_policy_path(None) == CANDIDATE
    assert load_policy().version == 2


def test_cli_arg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(POLICY_ENV_VAR, str(CANDIDATE))
    assert load_policy(SEED).version == 1


def test_service_uses_arg_policy() -> None:
    service = RouterService(policy=load_policy(CANDIDATE))
    response = service.dispatch("GET", "/policy")
    assert response.payload["version"] == 2


def test_service_uses_env_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(POLICY_ENV_VAR, str(CANDIDATE))
    service = RouterService()
    assert service.dispatch("GET", "/policy").payload["version"] == 2


def test_invalid_policy_path_raises() -> None:
    with pytest.raises(OSError):
        load_policy(ROOT / "does-not-exist.yaml")
