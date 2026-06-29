"""Tests for the ``cost-router policy`` subcommands and reusable policy ops."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy import diff_policies, load_default_policy, show_text, validate_errors
from policy.schema import PolicyTable
from router import cli

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "src" / "policy" / "seed_policy.yaml"
CANDIDATE = ROOT / "samples" / "policy" / "candidate.example.yaml"


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_show_text_lists_all_classes() -> None:
    text = show_text(load_default_policy())
    assert "policy v1" in text
    for cls in ("plan", "generate", "test", "validate", "repo_patch"):
        assert f"{cls}:" in text


def test_validate_errors_empty_for_seed() -> None:
    assert validate_errors(load_default_policy()) == []


def test_diff_reports_added_and_removed() -> None:
    base = PolicyTable.from_yaml(SEED).validate()
    candidate = PolicyTable.from_yaml(CANDIDATE).validate()
    diff = diff_policies(base, candidate)
    assert diff.changed
    assert "premium-max (removed)" in " ".join(diff.changes["repo_patch"])


def test_policy_show_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["policy", "show"]) == 0
    assert "candidates per class" in capsys.readouterr().out


def test_policy_no_subcommand_shows(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["policy"]) == 0
    assert "policy v1" in capsys.readouterr().out


def test_policy_validate_seed_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["policy", "validate", "--policy", str(SEED)]) == 0
    assert "OK: policy is valid" in capsys.readouterr().out


def test_policy_validate_candidate_ok() -> None:
    assert cli.main(["policy", "validate", "--policy", str(CANDIDATE)]) == 0


def test_policy_diff_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["policy", "diff", "--candidate", str(CANDIDATE)]) == 0
    out = capsys.readouterr().out
    assert "policy diff v1 -> v2" in out
    assert "removed" in out


def test_policy_simulate_candidate(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["policy", "simulate", "--policy", str(CANDIDATE), "--synth"]) == 0
    out = capsys.readouterr().out
    assert "tasks: 100" in out
    assert "by_class:" in out


def test_policy_validate_rejects_out_of_range(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 1\nclasses:\n  generate:\n"
        "    - {model: mini-fast, prior_pass: 2.0, prior_usd_resolved: 0.1}\n"
    )
    assert cli.main(["policy", "validate", "--policy", str(bad)]) == 1


def test_policy_validate_rejects_missing_classes(tmp_path: Path) -> None:
    bad = tmp_path / "partial.yaml"
    bad.write_text(
        "version: 1\nclasses:\n  generate:\n"
        "    - {model: mini-fast, prior_pass: 0.7, prior_usd_resolved: 0.1}\n"
    )
    assert cli.main(["policy", "validate", "--policy", str(bad)]) == 1


def test_policy_help_lists_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["policy", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for sub in ("show", "validate", "diff", "simulate", "regression"):
        assert sub in out
