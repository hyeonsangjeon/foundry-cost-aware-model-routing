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


def test_serve_help_lists_host_and_port(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["serve", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--host" in out
    assert "--port" in out


def test_serve_defaults_are_loopback() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["serve"])
    assert args.host == "127.0.0.1"
    assert args.port == 8000


# -- metrics store + Foundry emit -------------------------------------------

def test_experiment_run_records_metrics(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "history.jsonl"
    assert cli.main(["experiment", "run", "ensemble", "--metrics-store", str(store)]) == 0
    assert "metrics  recorded to" in capsys.readouterr().out
    assert store.is_file()
    rows = [json.loads(line) for line in store.read_text().splitlines() if line.strip()]
    assert rows[0]["experiment"] == "ensemble"
    assert rows[0]["ensemble_tax_usd"] == pytest.approx(0.364011, abs=1e-6)


def test_hero_records_metrics(tmp_path: Path) -> None:
    store = tmp_path / "history.jsonl"
    assert cli.main(["hero", "--metrics-store", str(store)]) == 0
    rows = [json.loads(line) for line in store.read_text().splitlines() if line.strip()]
    assert rows[0]["experiment"] == "hero"


def test_metrics_history_shows_recorded_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "history.jsonl"
    cli.main(["experiment", "run", "curated", "--metrics-store", str(store)])
    capsys.readouterr()
    assert cli.main(["metrics", "history", "--store", str(store)]) == 0
    out = capsys.readouterr().out
    assert "metrics history  (1 run(s)" in out
    assert "curated" in out
    assert "fanout_tax=$" in out


def test_metrics_history_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "history.jsonl"
    cli.main(["experiment", "run", "curated", "--metrics-store", str(store)])
    capsys.readouterr()
    assert cli.main(["metrics", "history", "--store", str(store), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["experiment"] == "curated"


def test_metrics_history_empty_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "empty.jsonl"
    assert cli.main(["metrics", "history", "--store", str(store)]) == 0
    assert "no recorded runs" in capsys.readouterr().out


def test_metrics_emit_offline_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["metrics", "emit", "ensemble"]) == 0
    out = capsys.readouterr().out
    assert "local capture (offline)" in out
    records = json.loads(out[out.index("[") :])
    names = {record["name"] for record in records}
    assert "router.ensemble.tax_usd" in names


def test_metrics_emit_marks_configured_with_connection_string(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(
        ["metrics", "emit", "hero", "--connection-string", "InstrumentationKey=abc"]
    )
    assert code == 0
    assert "Azure Foundry (configured)" in capsys.readouterr().out


def test_metrics_emit_unknown_experiment_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["metrics", "emit", "nope"]) == 1
    assert "metrics error" in capsys.readouterr().out


def test_bare_metrics_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["metrics"]) == 0
    assert "usage: cost-router metrics" in capsys.readouterr().out


def test_compare_default_prints_four_approaches(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compare"]) == 0
    out = capsys.readouterr().out
    assert "one problem, four ways   (measured = false)" in out
    assert "task  t-0003" in out
    for label in ("Cheapest model", "Premium model", "Ensemble (fan-out)", "Cost-aware router"):
        assert label in out
    # honest winners line: router wins cost, premium wins latency, and accuracy
    # is a pass/fail tally (3 of 4 pass) rather than a single crowned winner
    assert "cost: Cost-aware router" in out
    assert "latency: Premium model" in out
    assert "accuracy: 3 of 4 pass" in out


def test_compare_task_override(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compare", "--task", "t-0001"]) == 0
    assert "task  t-0001" in capsys.readouterr().out


def test_compare_prints_readable_problem(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compare", "--task", "t-0003"]) == 0
    out = capsys.readouterr().out
    # the authored problem statement is shown above the table so the run is
    # concrete: a title, the prompt a user would pose, and an acceptance line
    assert "problem   Patch parse_duration to accept combined units" in out
    assert "parse_duration" in out
    assert "expect:" in out


def test_compare_json_includes_problem(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compare", "--json", "--task", "t-0001"]) == 0
    arena = json.loads(capsys.readouterr().out)
    assert arena["problem"]["title"] == "slugify(title)"
    assert arena["labels"]["problem_basis"] == "authored-synthetic"


def test_compare_json_emits_single_arena(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compare", "--json", "--task", "t-0003"]) == 0
    arena = json.loads(capsys.readouterr().out)
    assert arena["task_id"] == "t-0003"
    by = {a["approach"]: a for a in arena["approaches"]}
    assert by["router"]["cost_usd"] == pytest.approx(0.032793, abs=1e-6)
    assert by["ensemble"]["cost_usd"] == pytest.approx(0.179844, abs=1e-6)


def test_compare_unknown_task_reports_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compare", "--task", "t-9999"]) == 2
    assert "unknown task 't-9999'" in capsys.readouterr().out
