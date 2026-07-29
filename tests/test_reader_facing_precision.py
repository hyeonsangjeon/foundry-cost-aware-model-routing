"""Reader-facing money precision.

Contract (see :data:`router.pricing.READER_FACING_USD_RENDERERS`):

* Human-readable surfaces show **two decimals** for totals and **four** for
  sub-cent amounts, so real per-task costs never collapse to ``$0.00``.
* Machine surfaces — ``--json`` payloads, the audit ledger, replay records —
  keep **canonical full precision** and are never routed through the reader
  formatters.

The reader-facing assertions render the declared surfaces from real runs and
inspect every emitted money token, rather than pattern-matching decimals across
the repository.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from router import cli
from router.pricing import (
    CANONICAL_PRECISION_SURFACES,
    READER_FACING_USD_RENDERERS,
    format_usd,
    format_usd_avg,
)

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"

#: A rendered money token is either a plain total (2 decimals) or a sub-cent
#: amount (4 decimals). Nothing else may reach a reader.
MONEY_TOKEN = re.compile(r"\$-?\d+\.(\d+)")


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def _money_decimals(text: str) -> list[int]:
    return [len(match.group(1)) for match in MONEY_TOKEN.finditer(text)]


def _assert_reader_precision(text: str) -> None:
    decimals = _money_decimals(text)
    assert decimals, "surface rendered no money token"
    bad = sorted({count for count in decimals if count not in (2, 4)})
    assert not bad, f"reader-facing surface emitted {bad}-decimal money in:\n{text}"


def _usd_values(node: object) -> list[float]:
    """Collect every ``*_usd`` numeric leaf from a nested machine record."""
    found: list[float] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if key.endswith("_usd"):
                    found.append(float(value))
            else:
                found.extend(_usd_values(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_usd_values(item))
    return found


# --------------------------------------------------------------------------
# formatter unit rules
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "$0.00"),
        (1.6591669, "$1.66"),
        (2.23, "$2.23"),
        (0.01, "$0.01"),
        (0.009999, "$0.0100"),
        (0.0041234, "$0.0041"),
        (0.000012, "$0.0000"),
        (-0.0041234, "$-0.0041"),
        (-1.5, "$-1.50"),
    ],
)
def test_format_usd_rule(value: float, expected: str) -> None:
    assert format_usd(value) == expected


def test_format_usd_avg_always_four_decimals() -> None:
    assert format_usd_avg(0.00412) == "$0.0041"
    assert format_usd_avg(2.5) == "$2.5000"


def test_format_usd_never_collapses_a_real_sub_cent_cost_to_zero() -> None:
    assert format_usd(0.0003) != "$0.00"


def test_declared_surfaces_are_documented() -> None:
    assert READER_FACING_USD_RENDERERS
    assert CANONICAL_PRECISION_SURFACES


# --------------------------------------------------------------------------
# declared reader-facing surfaces
# --------------------------------------------------------------------------


def test_replay_text_surface(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["replay", "--workload", str(WORKLOAD), "--synth"]) == 0
    _assert_reader_precision(capsys.readouterr().out)


def test_experiment_text_surface(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["experiment", "run", "hero"]) == 0
    _assert_reader_precision(capsys.readouterr().out)


def test_single_call_experiment_text_surface(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["experiment", "run", "single-call"]) == 0
    _assert_reader_precision(capsys.readouterr().out)


def test_measure_catalog_surface(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["measure", "catalog"]) == 0
    _assert_reader_precision(capsys.readouterr().out)


def test_foundry_live_recorded_surface(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["foundry", "live"]) == 0
    out = capsys.readouterr().out
    _assert_reader_precision(out)
    # The README quotes these exact rendered values.
    assert "routed cost (real): $0.02" in out
    assert "avg $/task        : $0.0041" in out


# --------------------------------------------------------------------------
# machine surfaces keep canonical precision
# --------------------------------------------------------------------------


def test_replay_json_keeps_canonical_precision(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["replay", "--workload", str(WORKLOAD), "--synth", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    traces = payload if isinstance(payload, list) else payload.get("traces", [])
    costs = [float(trace["cost_usd"]) for trace in traces if "cost_usd" in trace]
    assert costs, "replay --json exposed no machine cost field"
    assert any(round(cost, 2) != cost for cost in costs), (
        "machine JSON appears rounded to reader precision"
    )


def test_ledger_keeps_canonical_precision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert (
        cli.main(
            ["replay", "--workload", str(WORKLOAD), "--synth", "--ledger", str(ledger)]
        )
        == 0
    )
    capsys.readouterr()
    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line]
    assert records, "ledger wrote no records"
    costs = [value for record in records for value in _usd_values(record)]
    assert costs, "ledger exposed no machine cost field"
    assert any(round(cost, 2) != cost for cost in costs), (
        "ledger appears rounded to reader precision"
    )


def test_reader_and_machine_totals_agree_before_rounding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["replay", "--workload", str(WORKLOAD), "--synth", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    traces = payload if isinstance(payload, list) else payload.get("traces", [])
    total = sum(float(trace.get("cost_usd", 0.0)) for trace in traces)

    assert cli.main(["replay", "--workload", str(WORKLOAD), "--synth"]) == 0
    text = capsys.readouterr().out
    assert format_usd(total) in text
