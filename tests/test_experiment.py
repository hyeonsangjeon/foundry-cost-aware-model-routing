"""Tests for named offline experiments and the hero run mode."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from router import cli
from router.experiment import (
    Expectation,
    list_experiments,
    load_experiment,
    run_experiment,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_list_experiments_includes_hero_and_curated() -> None:
    names = [experiment.name for experiment in list_experiments()]
    assert "hero" in names
    assert "curated" in names
    assert names == sorted(names)


def test_load_hero_experiment_fields() -> None:
    hero = load_experiment("hero")
    assert hero.name == "hero"
    assert hero.synth is True
    assert hero.signals is None
    assert hero.spotlight == "auto"
    assert hero.expect.min_coverage == 1.0
    assert hero.expect.min_delta_pct == pytest.approx(0.20)


def test_load_experiment_by_path() -> None:
    path = ROOT / "experiments" / "curated.yaml"
    experiment = load_experiment(path)
    assert experiment.name == "curated"
    assert experiment.synth is False


def test_load_unknown_experiment_raises() -> None:
    with pytest.raises(ValueError, match="unknown experiment"):
        load_experiment("does-not-exist")


def test_hero_run_is_reproducible_and_green() -> None:
    result = run_experiment(load_experiment("hero"))
    summary = result.report.summary
    assert result.ok is True
    assert summary["tasks"] == 100
    assert summary["coverage"] == pytest.approx(1.0)
    assert summary["baseline_total_usd"] == pytest.approx(2.226910, abs=1e-6)
    assert summary["total_cost_usd"] == pytest.approx(1.659167, abs=1e-6)
    assert summary["delta_pct"] == pytest.approx(0.2549, abs=1e-3)
    assert summary["measured"] is False


def test_hero_spotlight_picks_biggest_accepted_saving() -> None:
    result = run_experiment(load_experiment("hero"))
    spotlight = result.spotlight
    assert spotlight is not None
    assert spotlight.task_id == "t-0078"
    assert spotlight.accepted is True
    assert spotlight.chosen_model == "mini-fast"
    assert spotlight.naive_model == "deep-reasoner"
    assert spotlight.ratio == pytest.approx(24.09, abs=0.1)
    assert spotlight.naive_usd > spotlight.routed_usd > 0.0


def test_curated_run_is_green_and_smaller() -> None:
    result = run_experiment(load_experiment("curated"))
    assert result.ok is True
    assert result.report.summary["tasks"] == 5
    assert result.report.summary["delta_pct"] == pytest.approx(0.5671, abs=1e-3)
    assert result.spotlight is not None
    assert result.spotlight.task_id == "t-0005"


def test_expectation_floor_can_fail() -> None:
    hero = load_experiment("hero")
    strict = replace(hero, expect=Expectation(min_coverage=1.0, min_delta_pct=0.99, min_tasks=1))
    result = run_experiment(strict)
    assert result.ok is False
    savings = next(check for check in result.checks if check.name == "savings")
    assert savings.ok is False


def test_explicit_spotlight_task_id() -> None:
    hero = load_experiment("hero")
    pinned = replace(hero, spotlight="t-0001")
    result = run_experiment(pinned)
    assert result.spotlight is not None
    assert result.spotlight.task_id == "t-0001"


def test_spotlight_can_be_disabled() -> None:
    hero = load_experiment("hero")
    off = replace(hero, spotlight="none")
    result = run_experiment(off)
    assert result.spotlight is None


def test_missing_spotlight_task_raises() -> None:
    hero = load_experiment("hero")
    bad = replace(hero, spotlight="t-9999")
    with pytest.raises(ValueError, match="spotlight task"):
        run_experiment(bad)


def test_experiment_to_dict_round_trips_shape() -> None:
    result = run_experiment(load_experiment("hero"))
    payload = result.to_dict()
    assert payload["ok"] is True
    assert payload["experiment"]["name"] == "hero"
    assert payload["spotlight"]["task_id"] == "t-0078"
    assert {check["name"] for check in payload["checks"]} == {"coverage", "savings", "tasks"}


def test_cli_hero_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["hero"]) == 0
    out = capsys.readouterr().out
    assert "experiment: hero" in out
    assert "before / after" in out
    assert "reproducibility  PASS" in out
    assert "spotlight  t-0078" in out


def test_cli_hero_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["hero", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["experiment"]["name"] == "hero"


def test_cli_experiment_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["experiment", "list"]) == 0
    out = capsys.readouterr().out
    assert "hero" in out
    assert "curated" in out


def test_cli_experiment_run_curated(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["experiment", "run", "curated"]) == 0
    assert "experiment: curated" in capsys.readouterr().out


def test_cli_experiment_run_unknown_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["experiment", "run", "nope"]) == 1
    assert "experiment error" in capsys.readouterr().out


def test_cli_hero_ledger_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "hero.jsonl"
    assert cli.main(["hero", "--ledger", str(ledger)]) == 0
    assert "ledger  path=" in capsys.readouterr().out
    assert ledger.is_file()
    assert cli.main(["ledger", "replay", "--ledger", str(ledger)]) == 0
    assert "status: PASS" in capsys.readouterr().out
