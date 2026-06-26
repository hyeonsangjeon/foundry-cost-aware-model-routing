"""Tests for the ``cost-router`` CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from router import cli

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
SIGNALS = ROOT / "samples" / "responses" / "routing-signals.sample.json"
PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_version_flag_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "cost-router 0.1.0" in capsys.readouterr().out


def test_no_subcommand_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    assert "cost-router 0.1.0" in capsys.readouterr().out


def test_replay_curated_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["replay"]) == 0
    assert "summary tasks=5 accepted=5 coverage=100.0%" in capsys.readouterr().out


def test_replay_synth_covers_full_workload(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["replay", "--synth"]) == 0
    assert "summary tasks=100 accepted=100 coverage=100.0%" in capsys.readouterr().out


def test_replay_json_emits_trace_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["replay", "--json"]) == 0
    traces = json.loads(capsys.readouterr().out)
    assert isinstance(traces, list)
    assert [trace["task_id"] for trace in traces] == [
        "t-0001",
        "t-0003",
        "t-0004",
        "t-0005",
        "t-0006",
    ]


def test_replay_accepts_explicit_paths(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(
        [
            "replay",
            "--workload",
            str(WORKLOAD),
            "--signals",
            str(SIGNALS),
            "--pricing",
            str(PRICING),
        ]
    )
    assert code == 0
    assert "summary tasks=5" in capsys.readouterr().out


def test_route_once_curated(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["route-once", "--task-id", "t-0003"]) == 0
    trace = json.loads(capsys.readouterr().out)
    assert trace["task_id"] == "t-0003"
    assert trace["class"] == "repo_patch"


def test_route_once_synth_reaches_uncurated_task(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["route-once", "--task-id", "t-0050", "--synth"]) == 0
    trace = json.loads(capsys.readouterr().out)
    assert trace["task_id"] == "t-0050"
    assert trace["chosen"] is not None


def test_route_once_unknown_task_id_errors() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["route-once", "--task-id", "t-9999"])
    assert "unknown task id: t-9999" in str(excinfo.value)


def test_route_once_curated_missing_signals_errors() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["route-once", "--task-id", "t-0002"])
    assert "no sample signals for task id: t-0002" in str(excinfo.value)


def test_evals_curated(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["evals"]) == 0
    out = capsys.readouterr().out
    assert "tasks: 5" in out
    assert "coverage: 100.0%" in out
    assert "reason_counts:" in out


def test_evals_synth_reports_savings(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["evals", "--synth"]) == 0
    out = capsys.readouterr().out
    assert "tasks: 100" in out
    assert "delta_pct: 25.5%" in out


def test_cli_output_is_deterministic(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["replay", "--synth", "--json"])
    first = capsys.readouterr().out
    cli.main(["replay", "--synth", "--json"])
    second = capsys.readouterr().out
    assert first == second
