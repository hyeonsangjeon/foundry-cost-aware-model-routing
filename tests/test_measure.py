"""Tests for the measured live-run harness (``router.measure``, BOLT Phase 0).

Network-free: every run is driven through a scripted fake :class:`MeasureClient`
so the dry-run estimate, snapshot layout (§3), deterministic replay, budget
guard, 429 retry accounting, prereg gate (D8), resume, honest ``measured``
labels and the range-contract validator are all pinned without egress.
"""

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from router import cli
from router.measure import (
    AttemptResult,
    MeasureCandidate,
    MeasuredContract,
    PreregDecision,
    RetryPolicy,
    build_catalog,
    build_publish_bundle,
    compute_summary,
    estimate_dry_run,
    evaluate_prereg,
    format_catalog,
    format_dry_run_table,
    load_prompt_workload,
    replay_measure,
    run_candidate,
    run_measure,
    verify_contract,
    workload_fingerprint,
)
from router.pricing import PricingTable
from router.validation import ValidationSpecError

PRICING = Path("samples/pricing/foundry-5series.yaml")
WORKLOAD = Path("samples/telemetry/curated-arena-live.sample.jsonl")


def _pricing() -> PricingTable:
    return PricingTable.from_yaml(PRICING)


def _workload() -> dict[str, dict]:
    return load_prompt_workload(WORKLOAD)


def _candidates() -> list[MeasureCandidate]:
    return [
        MeasureCandidate("gpt-5.4-nano", "gpt-5.4-nano"),
        MeasureCandidate("gpt-5.4", "gpt-5.4"),
    ]


def _fixed_clock():
    counter = itertools.count()
    return lambda: f"2026-07-26T00:00:{next(counter) % 60:02d}.000000+00:00"


def _prereg() -> PreregDecision:
    return PreregDecision(
        True, "abc123", "2026-07-25T00:00:00+00:00", "prereg committed before run"
    )


class ScriptedClient:
    """Deterministic fake: fixed usage/latency, optional 429 script per cell."""

    def __init__(self, *, throttle: dict[tuple[str, str], int] | None = None, provenance="live",
                 always_429: bool = False):
        self.throttle = dict(throttle or {})
        self.provenance = provenance
        self.always_429 = always_429
        self.calls: list[tuple[str, str]] = []

    def attempt(self, *, deployment, provider, task):
        key = (deployment, task["task_id"])
        self.calls.append(key)
        if self.always_429:
            return AttemptResult(http_status=429, latency_ms=1.0, provenance=self.provenance)
        remaining = self.throttle.get(key, 0)
        if remaining > 0:
            self.throttle[key] = remaining - 1
            return AttemptResult(http_status=429, latency_ms=1.0, provenance=self.provenance)
        usage = task.get("tokens") or {
            "input": 1000, "cached": 200, "output": 500, "reasoning": 100
        }
        return AttemptResult(
            http_status=200, model=deployment, usage=usage, latency_ms=12.3,
            provenance=self.provenance,
        )


def _run(tmp_path, client, **kwargs):
    defaults = dict(
        client=client, pricing=_pricing(), exp_id="curated",
        run_dir=tmp_path / "curated" / "RUN", run_id="RUN", n=2,
        retry=RetryPolicy(max_retries=3, base_backoff_ms=1.0),
        sleeper=lambda _s: None, clock=_fixed_clock(),
        now=datetime(2026, 7, 26, tzinfo=UTC), prereg=_prereg(),
    )
    defaults.update(kwargs)
    workload = defaults.pop("workload", _workload())
    candidates = defaults.pop("candidates", _candidates())
    return run_measure(workload, candidates, **defaults)


# --------------------------------------------------------------------------- #
# Dry-run estimate (no live calls)
# --------------------------------------------------------------------------- #


def test_dry_run_estimate_counts_and_budget():
    estimate = estimate_dry_run(_workload(), _candidates(), n=3, pricing=_pricing())
    assert estimate["tasks"] == 5
    assert estimate["candidates"] == 2
    assert estimate["calls"] == 5 * 2 * 3
    assert estimate["labels"]["measured"] is False
    assert estimate["est_total_usd"] > 0
    table = format_dry_run_table(estimate, budget_usd=estimate["est_total_usd"] + 1)
    assert "within budget" in table
    assert "NO live calls" in table
    over = format_dry_run_table(estimate, budget_usd=0.0)
    assert "OVER BUDGET" in over


# --------------------------------------------------------------------------- #
# Prompt-bearing schema loading (B2) + pre-flight catalog (B4/D12)
# --------------------------------------------------------------------------- #


def _write_jsonl(tmp_path, rows) -> Path:
    path = tmp_path / "wl.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_load_prompt_workload_reads_canonical_schema(tmp_path):
    path = _write_jsonl(
        tmp_path,
        [
            {
                "task_id": "t1",
                "class": "generate",
                "system_prompt": "be terse",
                "user_prompt": "write solve(n)",
                "validation": {"type": "regex", "pattern": "def\\s+solve"},
            },
            {"id": "t2", "prompt": "legacy field still works", "system": "legacy system"},
        ],
    )
    wl = load_prompt_workload(path)
    assert wl["t1"]["class"] == "generate"
    assert wl["t1"]["system"] == "be terse"  # system_prompt aliases to internal `system`
    assert wl["t1"]["prompt"] == "write solve(n)"  # user_prompt aliases to internal `prompt`
    assert wl["t1"]["validation"]["type"] == "regex"
    # back-compat: legacy prompt/system keys still load
    assert wl["t2"]["prompt"] == "legacy field still works"
    assert wl["t2"]["system"] == "legacy system"


def test_load_prompt_workload_rejects_bad_validation(tmp_path):
    path = _write_jsonl(
        tmp_path, [{"task_id": "t1", "user_prompt": "hi", "validation": {"type": "vibes"}}]
    )
    with pytest.raises(ValidationSpecError):
        load_prompt_workload(path)


def test_build_catalog_surfaces_prompts_validation_and_estimate(tmp_path):
    path = _write_jsonl(
        tmp_path,
        [
            {
                "task_id": "t1",
                "class": "generate",
                "system_prompt": "sys",
                "user_prompt": "do a thing",
                "validation": {"type": "contains", "value": "def"},
                "tokens": {"input": 100, "output": 50},
            },
            {"task_id": "t2", "user_prompt": "ungraded task"},  # no validation
        ],
    )
    wl = load_prompt_workload(path)
    catalog = build_catalog(wl, _candidates(), n=2, pricing=_pricing())
    assert catalog["graded_tasks"] == 1
    assert catalog["ungraded_tasks"] == 1
    assert catalog["workload_fingerprint"] == workload_fingerprint(wl)
    assert catalog["labels"]["measured"] is False
    t1 = catalog["tasks"][0]
    assert t1["user_prompt"] == "do a thing"
    assert t1["system_prompt"] == "sys"
    assert "contains" in t1["validation"]  # describe_rule summary
    assert catalog["tasks"][1]["validation"] is None
    # the dry-run estimate rides along
    assert catalog["estimate"]["calls"] == 2 * len(_candidates()) * 2

    text = format_catalog(catalog, budget_usd=catalog["estimate"]["est_total_usd"] + 1)
    assert "do a thing" in text
    assert "pass if" in text
    assert "NO calls made here" in text
    assert "within budget" in text
    assert "(ungraded — no rule)" in text


# --------------------------------------------------------------------------- #
# Snapshot layout (§3) + honest labels
# --------------------------------------------------------------------------- #


def test_run_writes_full_snapshot(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    run_dir = result.run_dir
    for name in (
        "manifest.json", "prereg.md", "traces.jsonl", "summary.json", "pricing.snapshot.yaml"
    ):
        assert (run_dir / name).is_file(), name
    # one trace row per (task × repeat × candidate) with no throttling
    rows = [json.loads(line) for line in (run_dir / "traces.jsonl").read_text().splitlines()]
    assert len(rows) == 5 * 2 * 2
    row = rows[0]
    for field in ("run_id", "exp_id", "task_id", "repeat_idx", "candidate_model", "attempt_idx",
                  "tokens", "latency_ms", "http_status", "retries", "backoff_ms_total",
                  "cost_usd", "pass", "score", "fail_reason", "labels", "ts"):
        assert field in row, field
    assert set(row["tokens"]) == {"input", "cached", "output", "reasoning"}
    # manifest fingerprints cover every payload file
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert set(manifest["fingerprints"]) == {
        "traces.jsonl", "summary.json", "pricing.snapshot.yaml", "prereg.md"
    }
    assert manifest["n"] == 2
    assert manifest["prereg"]["commit_hash"] == "abc123"
    assert manifest["labels"]["measured"] is True
    # D14: the input workload identity is sealed alongside the outputs
    assert manifest["schema_version"] == 2
    assert manifest["workload_fingerprint"] == workload_fingerprint(_workload())
    assert manifest["workload_fingerprint"].startswith("sha256:")


def test_workload_fingerprint_tracks_prompt_changes(tmp_path):
    base = {
        "t-0001": {"task_id": "t-0001", "class": "generate", "user_prompt": "write a foo"},
        "t-0002": {"task_id": "t-0002", "class": "validate", "user_prompt": "check the bar"},
    }
    same = {  # same content, different insertion order → same fingerprint
        "t-0002": {"class": "validate", "task_id": "t-0002", "user_prompt": "check the bar"},
        "t-0001": {"class": "generate", "task_id": "t-0001", "user_prompt": "write a foo"},
    }
    changed = json.loads(json.dumps(base))
    changed["t-0001"]["user_prompt"] = "write a foo differently"

    fp = workload_fingerprint(base)
    assert fp.startswith("sha256:")
    assert workload_fingerprint(same) == fp  # order-insensitive, content-identical
    assert workload_fingerprint(changed) != fp  # a changed prompt → a different experiment


def test_measured_label_true_only_for_live_provenance(tmp_path):
    live = _run(tmp_path / "a", ScriptedClient(provenance="live"))
    assert live.summary["labels"]["measured"] is True
    recorded = _run(tmp_path / "b", ScriptedClient(provenance="recorded"))
    assert recorded.summary["labels"]["measured"] is False


def test_summary_ungraded_without_grader(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    assert result.summary["coverage"] is None
    assert result.summary["labels"]["accuracy"] == "ungraded"


def test_summary_graded_with_grader(tmp_path):
    # grade nano as fail, gpt-5.4 as pass → coverage 0.5. A legacy usage grader
    # (bool return, content-unaware) still works via the 5-arg content-aware
    # signature: the extra ``content`` arg is simply ignored.
    def grader(task_id, task, model, usage, content=None):
        return model == "gpt-5.4"

    result = _run(tmp_path, ScriptedClient(), grader=grader)
    cov = result.summary["coverage"]
    assert cov is not None
    assert cov["basis"] == "graded"
    assert cov["coverage"] == pytest.approx(0.5)
    assert result.summary["labels"]["accuracy"] == "graded"
    # A bool grader sets no output hash, so the content-grading blocks stay off
    # and the run's summary is byte-identical to the pre-bridge shape.
    assert "grading" not in result.summary
    assert "quality" not in result.summary


# --------------------------------------------------------------------------- #
# Deterministic replay (§3.4)
# --------------------------------------------------------------------------- #


def test_replay_is_byte_identical(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    report = replay_measure(result.run_dir)
    assert report.ok
    assert report.summary_matches
    assert report.fingerprints_ok
    assert report.cost_mismatches == ()


def test_two_runs_produce_identical_traces(tmp_path):
    a = _run(tmp_path / "a", ScriptedClient())
    b = _run(tmp_path / "b", ScriptedClient())
    assert (a.run_dir / "traces.jsonl").read_bytes() == (b.run_dir / "traces.jsonl").read_bytes()
    assert (a.run_dir / "summary.json").read_bytes() == (b.run_dir / "summary.json").read_bytes()


def test_replay_detects_tampering(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    traces_path = result.run_dir / "traces.jsonl"
    lines = traces_path.read_text().splitlines()
    tampered = json.loads(lines[0])
    tampered["cost_usd"] = 999.0
    lines[0] = json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    traces_path.write_text("\n".join(lines) + "\n")
    report = replay_measure(result.run_dir)
    assert not report.ok
    # either the fingerprint breaks or the recomputed cost no longer matches
    assert (not report.fingerprints_ok) or report.cost_mismatches


# --------------------------------------------------------------------------- #
# Publish bundle (C8) — public-mockup export with tenant pricing masked
# --------------------------------------------------------------------------- #


def test_publish_bundle_keeps_result_and_masks_tenant_pricing(tmp_path):
    result = _run(
        tmp_path,
        ScriptedClient(),
        pricing_path="samples/pricing/foundry-5series.yaml",
        endpoint="https://aoai-secret-name.cognitiveservices.azure.com",
        region="eastus",
        git_commit="deadbeef",
    )
    bundle = build_publish_bundle(result.run_dir)
    # The measured RESULT is kept (that is the whole point of the public mockup).
    assert bundle["provenance"]["measured"] is True
    assert bundle["result"]["cost"]["savings_pct"] == result.summary["cost"]["savings_pct"]
    assert bundle["n"] == result.summary["n"]
    assert bundle["git_commit"] == "deadbeef"
    # Tenant-specific rate card is masked: no absolute pricing path or raw rates.
    blob = json.dumps(bundle)
    assert "samples/pricing" not in blob
    assert "per_million" not in blob and "input_per_1k" not in blob
    # Endpoint is host-only (scheme://netloc), matching status() redaction.
    assert bundle["provenance"]["endpoint"] == (
        "https://aoai-secret-name.cognitiveservices.azure.com"
    )
    assert bundle["provenance"]["pricing"]["note"].startswith("tenant rate card masked")


def test_publish_refuses_unreplayable_snapshot(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    # Corrupt the sealed summary so the snapshot no longer replays.
    (result.run_dir / "summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="does not replay"):
        build_publish_bundle(result.run_dir)


def test_publish_bundle_is_deterministic(tmp_path):
    from router.measure import publish_bundle_json

    result = _run(tmp_path, ScriptedClient())
    assert publish_bundle_json(result.run_dir) == publish_bundle_json(result.run_dir)


# --------------------------------------------------------------------------- #
# Budget guard (partial snapshot)
# --------------------------------------------------------------------------- #


def test_budget_guard_halts_and_marks_partial(tmp_path):
    result = _run(tmp_path, ScriptedClient(), budget_usd=0.02)
    assert result.partial is True
    assert result.summary["labels"]["partial"] is True
    assert result.manifest["partial"] is True
    assert "budget cap reached" in (result.stopped_reason or "")
    # a partial snapshot must still replay clean
    assert replay_measure(result.run_dir).ok
    # and it stopped before running the full 20-cell sweep
    assert result.summary["attempts"] < 5 * 2 * 2


def test_progress_hook_fires_per_cell(tmp_path):
    events: list[dict] = []
    result = _run(tmp_path, ScriptedClient(), progress=events.append)
    cells = [e for e in events if e.get("event") == "cell_done"]
    assert len(cells) == 5 * 2 * 2  # every (task × repeat × candidate) cell
    # cells_done climbs monotonically to the full total; cost never decreases
    assert [e["cells_done"] for e in cells] == list(range(1, len(cells) + 1))
    assert cells[-1]["cells_done"] == cells[-1]["cells_total"] == 20
    assert all(a["running_cost_usd"] <= b["running_cost_usd"]
               for a, b in zip(cells, cells[1:], strict=False))
    assert cells[-1]["running_cost_usd"] == pytest.approx(result.summary["cost"]["total_usd"])
    # a clean scripted run books no throttles or failures
    assert cells[-1]["throttles"] == 0 and cells[-1]["failures"] == 0


def test_progress_hook_reports_budget_halt_and_throttles(tmp_path):
    events: list[dict] = []
    client = ScriptedClient(throttle={("gpt-5.4-nano", "t-0001"): 1})
    _run(tmp_path, client, budget_usd=0.02, progress=events.append)
    assert any(e.get("event") == "budget_halt" for e in events)
    halt = next(e for e in events if e.get("event") == "budget_halt")
    assert halt["cells_done"] < halt["cells_total"]  # stopped early
    assert "budget cap reached" in halt["stopped_reason"]
    # the one throttled attempt is tallied on the running counters
    assert max(e.get("throttles", 0) for e in events) >= 1


# --------------------------------------------------------------------------- #
# 429 retry accounting (§3.2 / D6)
# --------------------------------------------------------------------------- #


def test_429_retry_records_one_row_per_attempt(tmp_path):
    # nano on t-0001 gets one 429 then succeeds
    client = ScriptedClient(throttle={("gpt-5.4-nano", "t-0001"): 1})
    result = _run(tmp_path, client)
    rows = [json.loads(line) for line in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    cell = [r for r in rows if r["candidate_model"] == "gpt-5.4-nano"
            and r["task_id"] == "t-0001" and r["repeat_idx"] == 1]
    assert len(cell) == 2  # one 429 attempt row + one success row
    assert cell[0]["http_status"] == 429
    assert cell[0]["fail_reason"] == "throttled_429"
    assert cell[1]["http_status"] == 200
    assert cell[1]["retries"] == 1
    assert cell[1]["backoff_ms_total"] > 0
    throttle = result.summary["throttle"]
    assert throttle["http_429"] == 1
    assert throttle["retries"] == 1
    assert throttle["throttle_exhausted"] == 0


def test_throttle_exhaustion_is_a_recorded_failure(tmp_path):
    client = ScriptedClient(always_429=True)
    result = _run(
        tmp_path, client, workload={"t-0001": _workload()["t-0001"]},
        candidates=[MeasureCandidate("gpt-5.4-nano", "gpt-5.4-nano")],
        n=1, retry=RetryPolicy(max_retries=2, base_backoff_ms=1.0),
    )
    rows = [json.loads(line) for line in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    assert len(rows) == 3  # 3 attempts, all 429
    assert rows[-1]["fail_reason"] == "throttle_exhausted"
    assert result.summary["calls"] == 0
    assert result.summary["throttle"]["throttle_exhausted"] == 1
    assert len(result.summary["failures"]) == 3
    assert replay_measure(result.run_dir).ok


# --------------------------------------------------------------------------- #
# §8 acceptance: stub-HTTP wire-request counts (smoke=1, benchmark=1+retries)
# --------------------------------------------------------------------------- #


class _CountingClient:
    """Counts outbound attempts and replays a fixed HTTP status script."""

    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.calls = 0

    def attempt(self, *, deployment, provider, task):
        idx = min(self.calls, len(self.statuses) - 1)
        status = self.statuses[idx]
        self.calls += 1
        if 200 <= status < 300:
            return AttemptResult(
                http_status=status, model=deployment,
                usage={"input": 100, "cached": 0, "output": 50, "reasoning": 0},
                latency_ms=1.0, provenance="live",
            )
        return AttemptResult(http_status=status, latency_ms=1.0, provenance="live")


def _drive(client, *, max_retries: int):
    task = {"task_id": "t-0001", "prompt": "x", "tokens": {"input": 100, "output": 50}}
    return run_candidate(
        client, task, MeasureCandidate("gpt-5.4-nano", "gpt-5.4-nano"),
        run_id="RUN", exp_id="curated", repeat_idx=1, pricing=_pricing(),
        retry=RetryPolicy(max_retries=max_retries, base_backoff_ms=1.0),
        sleeper=lambda _s: None,
    )


@pytest.mark.parametrize("status", [429, 500, 503])
def test_smoke_sends_exactly_one_wire_request(status: int) -> None:
    # Smoke = zero runner retries: a single outbound request, even on 429/5xx.
    client = _CountingClient([status])
    _drive(client, max_retries=0)
    assert client.calls == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_benchmark_sends_one_plus_configured_retries(status: int) -> None:
    # Benchmark = 1 + configured runner retries on a persistent 429/5xx.
    client = _CountingClient([status])
    _drive(client, max_retries=3)
    assert client.calls == 4  # 1 initial + 3 retries


def test_5xx_then_success_stops_retrying() -> None:
    client = _CountingClient([503, 200])
    rows, final = _drive(client, max_retries=3)
    assert client.calls == 2  # one 5xx, then the success — no further attempts
    assert final is not None and final.ok
    assert rows[0]["fail_reason"] == "retry_http_503"


def test_4xx_client_error_is_never_retried() -> None:
    client = _CountingClient([400])
    _drive(client, max_retries=3)
    assert client.calls == 1  # a 4xx is fatal; the runner does not retry it


def test_timeout_is_not_retried_and_seals_as_unconfirmed() -> None:
    # A 408 read timeout may leave the request in flight → the runner does not
    # retry (avoids double charge); it records the attempt as a timeout failure.
    client = _CountingClient([408])
    rows, final = _drive(client, max_retries=3)
    assert client.calls == 1
    assert final is None
    assert rows[-1]["fail_reason"] == "timeout"


def test_http_error_is_non_retryable_failure(tmp_path):
    class ErrorClient:
        def attempt(self, *, deployment, provider, task):
            return AttemptResult(http_status=400, latency_ms=1.0, error="bad request")

    result = _run(
        tmp_path, ErrorClient(), workload={"t-0001": _workload()["t-0001"]},
        candidates=[MeasureCandidate("gpt-5.4", "gpt-5.4")], n=1,
    )
    rows = [json.loads(line) for line in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["fail_reason"] == "http_400"
    assert result.summary["throttle"]["http_429"] == 0


# --------------------------------------------------------------------------- #
# prereg gate (D8)
# --------------------------------------------------------------------------- #


def test_prereg_gate_refuses_uncommitted(tmp_path):
    pf = tmp_path / "prereg.md"
    pf.write_text("expected coverage ~1.0\n")
    started = datetime.now(UTC)
    decision = evaluate_prereg(pf, run_started_at=started, committed_at_fn=lambda _p: None)
    assert decision.allowed is False


def test_prereg_gate_bypass_is_recorded(tmp_path):
    pf = tmp_path / "prereg.md"
    pf.write_text("x\n")
    decision = evaluate_prereg(
        pf, run_started_at=datetime.now(UTC), allow_no_prereg=True, committed_at_fn=lambda _p: None
    )
    assert decision.allowed is True
    assert decision.bypassed is True


def test_prereg_gate_requires_commit_before_run(tmp_path):
    pf = tmp_path / "prereg.md"
    pf.write_text("expected coverage ~1.0\n")
    started = datetime(2026, 7, 26, tzinfo=UTC)
    after = evaluate_prereg(
        pf, run_started_at=started,
        committed_at_fn=lambda _p: ("h", "2026-07-27T00:00:00+00:00"),
    )
    assert after.allowed is False
    before = evaluate_prereg(
        pf, run_started_at=started,
        committed_at_fn=lambda _p: ("hash9", "2026-07-25T00:00:00+00:00"),
    )
    assert before.allowed is True
    assert before.commit_hash == "hash9"


# --------------------------------------------------------------------------- #
# Resume / checkpoint
# --------------------------------------------------------------------------- #


def test_resume_completes_remaining_cells(tmp_path):
    run_dir = tmp_path / "curated" / "RUN"
    # first pass halts on budget after a couple of cells
    first = _run(tmp_path, ScriptedClient(), run_dir=run_dir, budget_usd=0.02)
    assert first.partial is True
    done_after_first = first.summary["attempts"]
    # resume the same run id with no budget → finishes the sweep
    second = _run(tmp_path, ScriptedClient(), run_dir=run_dir, resume=True, budget_usd=None)
    assert second.partial is False
    assert second.summary["attempts"] == 5 * 2 * 2
    assert second.summary["attempts"] > done_after_first
    assert replay_measure(second.run_dir).ok


# --------------------------------------------------------------------------- #
# Measured range-contract (§7.2)
# --------------------------------------------------------------------------- #


def test_contract_pass_and_fail(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    summary = result.summary
    ok = verify_contract(summary, MeasuredContract(min_savings_pct=10.0, max_failure_rate=0.5))
    assert all(c.ok for c in ok if c.name != "freshness")
    bad = verify_contract(summary, MeasuredContract(min_savings_pct=99.9))
    assert any(c.name == "savings_floor" and not c.ok for c in bad)


def test_contract_freshness_warns_on_stale(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    stale_manifest = {"timestamp": "2000-01-01T00:00:00+00:00"}
    checks = verify_contract(result.summary, MeasuredContract(), manifest=stale_manifest)
    fresh = [c for c in checks if c.name == "freshness"]
    assert fresh and fresh[0].ok is False and "STALE" in fresh[0].detail


def test_contract_coverage_floor_needs_grader(tmp_path):
    result = _run(tmp_path, ScriptedClient())  # ungraded
    checks = verify_contract(result.summary, MeasuredContract(min_coverage=0.9))
    coverage = [c for c in checks if c.name == "coverage_floor"]
    assert coverage and coverage[0].ok is False


# --------------------------------------------------------------------------- #
# CLI surface
# --------------------------------------------------------------------------- #


def test_cli_measure_run_dry_run_gate(capsys):
    code = cli.main([
        "measure", "run", "curated",
        "--candidates", "gpt-5.4-nano,gpt-5.4", "--n", "3", "--budget-usd", "5",
    ])
    assert code == 2  # no --live → estimate-only gate
    out = capsys.readouterr().out
    assert "dry-run cost estimate" in out
    assert "no live calls were made" in out


def test_cli_measure_catalog_previews_prompts(capsys):
    code = cli.main([
        "measure", "catalog", "preview",
        "--workload", str(WORKLOAD),
        "--candidates", "gpt-5.4-nano,gpt-5.4",
        "--pricing", str(PRICING), "--n", "2", "--budget-usd", "5",
    ])
    assert code == 0  # preview only, never a live gate
    out = capsys.readouterr().out
    assert "prompt catalog" in out
    assert "workload fingerprint: sha256:" in out
    assert "no live calls" in out.lower()


def test_cli_measure_replay_and_verify(tmp_path, capsys):
    result = _run(tmp_path, ScriptedClient())
    code = cli.main(["measure", "replay", "--run", str(result.run_dir)])
    assert code == 0
    assert "status: PASS" in capsys.readouterr().out

    contract = tmp_path / "contract.yaml"
    contract.write_text("expect:\n  min_savings_pct: 10\n  max_failure_rate: 0.5\n")
    code = cli.main(
        ["measure", "verify", "--run", str(result.run_dir), "--contract", str(contract)]
    )
    assert code == 0
    assert "status: PASS" in capsys.readouterr().out


def test_cli_measure_replay_fails_on_tamper(tmp_path, capsys):
    result = _run(tmp_path, ScriptedClient())
    summary_path = result.run_dir / "summary.json"
    data = json.loads(summary_path.read_text())
    data["cost"]["total_usd"] = 42.0
    summary_path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    code = cli.main(["measure", "replay", "--run", str(result.run_dir)])
    assert code == 1
    assert "status: FAIL" in capsys.readouterr().out


def test_compute_summary_is_pure_and_order_stable():
    pricing = _pricing()
    traces = [
        {"task_id": "t1", "repeat_idx": 1, "candidate_model": "gpt-5.4-nano", "attempt_idx": 1,
         "http_status": 200, "retries": 0, "backoff_ms_total": 0.0, "latency_ms": 10.0,
         "cost_usd": pricing.cost_usd("gpt-5.4-nano", {"input": 100, "output": 50}),
         "tokens": {"input": 100, "cached": 0, "output": 50, "reasoning": 0},
         "pass": None, "score": None, "fail_reason": None, "labels": {"measured": True}},
    ]
    a = compute_summary(traces, pricing, exp_id="e", run_id="r", n=1,
                        task_ids=["t1"], candidate_models=["gpt-5.4-nano"], partial=False)
    b = compute_summary(traces, pricing, exp_id="e", run_id="r", n=1,
                        task_ids=["t1"], candidate_models=["gpt-5.4-nano"], partial=False)
    assert a == b
    assert a["integrity"]["cost_mismatches"] == []


# --------------------------------------------------------------------------- #
# RunHooks — per-cell gate/observer seam (03C cockpit uses this)
# --------------------------------------------------------------------------- #


def test_run_hooks_observe_every_dispatched_cell(tmp_path):
    from router.measure import CellId, RunHooks

    seen: list[CellId] = []
    after: list[tuple[CellId, int]] = []
    hooks = RunHooks(
        before_cell=lambda cell: (seen.append(cell), None)[1],
        after_cell=lambda cell, rows: after.append((cell, len(rows))),
    )
    result = _run(tmp_path, ScriptedClient(), n=1, hooks=hooks)
    planned = len(_workload()) * 1 * len(_candidates())
    assert len(seen) == planned  # one before_cell per logical cell
    assert len(after) == planned
    assert result.summary["labels"]["partial"] is False
    assert {c.model for c in seen} == {"gpt-5.4-nano", "gpt-5.4"}


def test_run_hooks_before_cell_halts_and_seals_partial(tmp_path):
    from router.measure import CellId, RunHooks

    dispatched: list[CellId] = []

    def _before(cell: CellId) -> str | None:
        if len(dispatched) >= 2:
            return "aborted by operator"
        dispatched.append(cell)
        return None

    result = _run(tmp_path, ScriptedClient(), n=1, hooks=RunHooks(before_cell=_before))
    rows = [
        json.loads(line)
        for line in (result.run_dir / "traces.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(dispatched) == 2  # halted before the 3rd cell dispatched
    assert len(rows) == 2  # only the admitted cells produced trace rows
    assert result.summary["labels"]["partial"] is True
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["stopped_reason"] == "aborted by operator"


def test_run_hooks_default_none_leaves_measured_path_unchanged(tmp_path):
    # Sealed output must be byte-identical whether hooks=None or hooks=RunHooks().
    from router.measure import RunHooks

    a = _run(tmp_path / "a", ScriptedClient(), n=1)
    b = _run(tmp_path / "b", ScriptedClient(), n=1, hooks=RunHooks())
    assert (a.run_dir / "summary.json").read_text() == (b.run_dir / "summary.json").read_text()
