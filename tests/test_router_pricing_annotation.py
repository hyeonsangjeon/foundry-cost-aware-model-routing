"""Pin the versioned Model Router pricing annotation and its fail-closed enforcement.

Model Router pricing is composite — a router input-token markup plus the
resolved underlying model's input and output charges — and the committed
measured artifacts priced routed calls at the underlying rate alone. The
artifacts stay byte-identical; a versioned annotation carries the correction.

These tests prove three things:

1. the originals are untouched and every original hash still verifies;
2. a missing, loosened, or hash-mismatched annotation withholds Model Router
   cost and savings on every renderer, publisher, replay summary, static build,
   and CLI display rather than falling back to the unannotated amount;
3. direct-model arms are never downgraded by the router-arm correction.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from router import annotations as ann
from router import cli
from router.annotations import (
    AnnotationError,
    load_router_pricing_annotation,
    router_cost_disclosure,
    savings_claim_allowed,
)
from router.ledger import verify_measured_ledger
from router.server import RouterService

REPO = Path(__file__).resolve().parents[1]
ANNOTATION = REPO / "samples" / "annotations" / "legacy-router-pricing.annotation.json"
ARENA = REPO / "samples" / "responses" / "foundry-arena-measured.json"
LEDGER = REPO / "samples" / "ledger" / "arena-measured.ledger.jsonl"
USAGE = REPO / "samples" / "responses" / "model-router-usage.sample.json"

DIRECT_ARMS = ("cheapest", "premium", "ensemble")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clone_tree(tmp_path: Path) -> Path:
    """Copy the annotated artifacts into a writable tree so tampering is safe."""

    root = tmp_path / "repo"
    for source in (ANNOTATION, ARENA, LEDGER, USAGE):
        target = root / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _annotation_path(root: Path) -> Path:
    return root / ANNOTATION.relative_to(REPO)


def _write_annotation(root: Path, mutate) -> Path:
    path = _annotation_path(root)
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the originals are evidence: unchanged bytes, unchanged hashes
# --------------------------------------------------------------------------


def test_annotation_matches_the_artifacts_it_annotates() -> None:
    annotation = load_router_pricing_annotation()
    by_path = {artifact.path: artifact for artifact in annotation.artifacts}
    assert set(by_path) == {
        "samples/responses/foundry-arena-measured.json",
        "samples/ledger/arena-measured.ledger.jsonl",
        "samples/responses/model-router-usage.sample.json",
    }
    for artifact in annotation.artifacts:
        target = REPO / artifact.path
        assert _sha256(target) == artifact.sha256
        assert target.stat().st_size == artifact.size_bytes
        assert artifact.immutable is True


def test_original_ledger_hashes_still_verify() -> None:
    """The annotation adds no bytes to the ledger, so its own audit is unchanged."""

    report = verify_measured_ledger(LEDGER)
    assert report.ok
    assert report.records == 5
    assert report.replayed == 5
    assert report.mismatches == ()


def test_annotation_reproduces_the_sealed_hash_chain() -> None:
    annotation = load_router_pricing_annotation()
    ledger = next(a for a in annotation.artifacts if a.path.endswith(".jsonl"))
    records = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line]
    assert tuple(r["record_hash"] for r in records) == ledger.record_hashes
    assert ledger.chain_head == records[-1]["record_hash"]
    # The chain the annotation quotes is the chain the ledger actually links.
    assert records[0]["previous_hash"] is None
    for earlier, later in zip(records, records[1:], strict=False):
        assert later["previous_hash"] == earlier["record_hash"]


# --------------------------------------------------------------------------
# the annotation says what is incomplete, and refuses to say less
# --------------------------------------------------------------------------


def test_annotation_marks_router_cost_incomplete_and_unclaimable() -> None:
    annotation = load_router_pricing_annotation()
    assert annotation.pricing_incomplete is True
    assert annotation.publishable is False
    assert annotation.savings_claim_allowed is False
    assert annotation.reason_code == "missing_router_input_markup"
    assert annotation.repriced is False
    assert annotation.reprice_reason


def test_annotation_scope_covers_only_the_router_arm() -> None:
    annotation = load_router_pricing_annotation()
    assert annotation.covers_arm("router") is True
    assert annotation.covers_deployment("model-router") is True
    for arm in DIRECT_ARMS:
        assert annotation.covers_arm(arm) is False


# --------------------------------------------------------------------------
# tamper and mismatch fail closed
# --------------------------------------------------------------------------


def test_tampered_artifact_fails_closed(tmp_path: Path) -> None:
    root = _clone_tree(tmp_path)
    target = root / "samples" / "responses" / "foundry-arena-measured.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="does not match its recorded hash"):
        load_router_pricing_annotation(_annotation_path(root))


def test_tampered_ledger_record_hash_fails_closed(tmp_path: Path) -> None:
    root = _clone_tree(tmp_path)
    path = _write_annotation(
        root,
        lambda data: data["evidence_artifacts"][1]["record_hashes"].__setitem__(0, "0" * 64),
    )
    with pytest.raises(AnnotationError, match="record hashes do not match"):
        load_router_pricing_annotation(path)


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    root = _clone_tree(tmp_path)
    (root / "samples" / "ledger" / "arena-measured.ledger.jsonl").unlink()
    with pytest.raises(AnnotationError, match="is missing"):
        load_router_pricing_annotation(_annotation_path(root))


def test_missing_annotation_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(AnnotationError, match="not found"):
        load_router_pricing_annotation(root=tmp_path)


def test_loosened_effects_fail_closed(tmp_path: Path) -> None:
    """Flipping the flags without a proven reprice is treated as tampering."""

    root = _clone_tree(tmp_path)
    path = _write_annotation(
        root, lambda data: data["effects"].update({"savings_claim_allowed": True})
    )
    with pytest.raises(AnnotationError, match="without a proven reprice"):
        load_router_pricing_annotation(path)


def test_claimed_reprice_without_pinned_rates_fails_closed(tmp_path: Path) -> None:
    root = _clone_tree(tmp_path)

    def mutate(data: dict) -> None:
        data["effects"].update(
            {"pricing_incomplete": False, "publishable": True, "savings_claim_allowed": True}
        )
        data["reprice"]["repriced"] = True

    path = _write_annotation(root, mutate)
    with pytest.raises(AnnotationError, match="without a pinned rate basis"):
        load_router_pricing_annotation(path)


def test_unsupported_schema_version_fails_closed(tmp_path: Path) -> None:
    root = _clone_tree(tmp_path)
    path = _write_annotation(root, lambda data: data.update({"schema_version": 99}))
    with pytest.raises(AnnotationError, match="unsupported annotation schema_version"):
        load_router_pricing_annotation(path)


def test_malformed_annotation_fails_closed(tmp_path: Path) -> None:
    root = _clone_tree(tmp_path)
    path = _annotation_path(root)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(AnnotationError, match="not valid JSON"):
        load_router_pricing_annotation(path)


def test_disclosure_never_raises_and_defaults_to_the_strictest_stance() -> None:
    disclosure = router_cost_disclosure(Path("/nonexistent/annotation.json"))
    assert disclosure["annotation_available"] is False
    assert disclosure["pricing_incomplete"] is True
    assert disclosure["publishable"] is False
    assert disclosure["savings_claim_allowed"] is False
    assert savings_claim_allowed(disclosure) is False
    assert disclosure["error"]


# --------------------------------------------------------------------------
# every renderer, publisher, replay summary, and CLI display enforces it
# --------------------------------------------------------------------------


def test_snapshot_publisher_withholds_the_router_savings_figure() -> None:
    source = json.loads(ARENA.read_text(encoding="utf-8"))
    # The stored snapshot still carries its original router-versus-premium
    # figure; the publisher is what refuses to hand it on.
    assert source["arm_totals"]["router"]["total_cost_usd"] > 0
    payload = RouterService().dispatch(
        "POST", "/fleet/run", body=json.dumps({"roles": {}}).encode()
    ).payload
    report = payload["report"]
    assert report["router_vs_premium_savings_pct"] is None
    disclosure = report["router_cost_disclosure"]
    assert disclosure["annotation_available"] is True
    assert disclosure["savings_claim_allowed"] is False
    assert disclosure["reason_code"] == "missing_router_input_markup"


def test_snapshot_publisher_keeps_direct_model_costs_intact() -> None:
    payload = RouterService().dispatch(
        "POST", "/fleet/run", body=json.dumps({"roles": {}}).encode()
    ).payload
    totals = payload["report"]["arm_totals"]
    source = json.loads(ARENA.read_text(encoding="utf-8"))["arm_totals"]
    for arm in DIRECT_ARMS:
        assert totals[arm]["total_cost_usd"] == source[arm]["total_cost_usd"]
    # The router amount is retained as historical output, not deleted or altered.
    assert totals["router"]["total_cost_usd"] == source["router"]["total_cost_usd"]


def test_measured_replay_reports_the_disclosure(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["ledger", "measured-replay", "--ledger", str(LEDGER)]) == 0
    out = capsys.readouterr().out
    assert "status: PASS" in out
    assert "router arm cost is pricing incomplete" in out
    assert "missing Router input markup" in out


def test_measured_replay_fails_closed_without_the_annotation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ann, "DEFAULT_ANNOTATION_RELPATH", Path("samples/annotations/gone.json"))
    assert cli.main(["ledger", "measured-replay", "--ledger", str(LEDGER)]) == 1
    out = capsys.readouterr().out
    assert "status: FAIL" in out
    assert "annotation not found" in out
    # The withheld run must not print a PASS or a re-derived cost claim.
    assert "status: PASS" not in out


def test_foundry_live_display_carries_the_disclosure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["foundry", "live"]) == 0
    out = capsys.readouterr().out
    assert "routed cost†" in out
    assert "omits the router input-token markup" in out
    assert "cheaper" not in out


def test_dashboard_fails_closed_without_a_disclosure() -> None:
    from router.dashboard import DASHBOARD_HTML

    assert "router_cost_disclosure" in DASHBOARD_HTML
    assert "savings_claim_allowed === true" in DASHBOARD_HTML


def test_static_build_publishes_no_router_savings(tmp_path: Path) -> None:
    import importlib.util
    import sys

    script = REPO / "scripts" / "build_static_site.py"
    spec = importlib.util.spec_from_file_location("build_static_site_z6", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        out = tmp_path / "site"
        module.build(out)
    finally:
        sys.modules.pop(spec.name, None)
    for payload in out.glob("*.json"):
        assert "router_vs_premium_savings_pct" not in payload.read_text(encoding="utf-8")
    assert "router_cost_disclosure" in (out / "index.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# direct-model arms are never downgraded by the router-arm correction
# --------------------------------------------------------------------------


def test_annotation_names_the_arms_it_does_not_touch() -> None:
    annotation = load_router_pricing_annotation()
    assert annotation.affected_arms == ("router",)
    assert set(annotation.unaffected_arms) == set(DIRECT_ARMS)
    assert not set(annotation.unaffected_arms).intersection(annotation.affected_arms)
    disclosure = annotation.to_disclosure()
    assert set(disclosure["unaffected_arms"]) == set(DIRECT_ARMS)


def test_unaffected_arms_may_not_overlap_the_affected_arms(tmp_path: Path) -> None:
    """Declaring the router 'unaffected' would silently erase the correction."""

    root = _clone_tree(tmp_path)

    def loosen(data: dict) -> None:
        data["scope"].setdefault("unaffected", {})["arms"] = ["premium", "router"]

    path = _write_annotation(root, loosen)
    with pytest.raises(AnnotationError) as excinfo:
        load_router_pricing_annotation(path=path)
    assert "overlaps scope.affected_arms" in str(excinfo.value)


def test_failsafe_disclosure_claims_no_arm_is_unaffected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no annotation we cannot vouch for any arm, so we vouch for none."""

    monkeypatch.setattr(ann, "DEFAULT_ANNOTATION_RELPATH", "samples/annotations/missing.json")
    disclosure = router_cost_disclosure()
    assert disclosure["annotation_available"] is False
    assert disclosure["unaffected_arms"] == []
    assert savings_claim_allowed(disclosure) is False


def test_direct_model_arm_costs_survive_the_correction_verbatim() -> None:
    source = json.loads(ARENA.read_text(encoding="utf-8"))
    payload = RouterService().dispatch(
        "POST", "/fleet/run", body=json.dumps({"roles": {}}).encode()
    ).payload
    published = payload["report"]["arm_totals"]
    for arm in DIRECT_ARMS:
        assert published[arm]["total_cost_usd"] == source["arm_totals"][arm]["total_cost_usd"]
    # The router amount is retained as historical output too — annotated, not erased.
    assert published["router"]["total_cost_usd"] == source["arm_totals"]["router"]["total_cost_usd"]


def test_arena_display_marks_only_the_router_arm(capsys: pytest.CaptureFixture[str]) -> None:
    from router.foundry_arena import FleetSlate

    report = RouterService().dispatch(
        "POST", "/fleet/run", body=json.dumps({"roles": {}}).encode()
    ).payload["report"]
    cli._print_arena_report(report, FleetSlate())
    out = capsys.readouterr().out
    for line in out.splitlines():
        arm = line.strip().split(" ")[0] if line.strip() else ""
        if arm in DIRECT_ARMS:
            assert "†" not in line, line
        if arm == "router" and "$" in line:
            assert "†" in line, line
    assert "unaffected (direct-model, never charged the markup)" in out
    for arm in DIRECT_ARMS:
        assert arm in out


# --------------------------------------------------------------------------
# an unvouched amount is withheld, not printed beside a "withheld" footnote
# --------------------------------------------------------------------------


def _hide_annotation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ann, "DEFAULT_ANNOTATION_RELPATH", "samples/annotations/absent.json")


def test_amount_is_showable_only_when_an_annotation_vouches_for_it() -> None:
    assert ann.historical_amount_showable(router_cost_disclosure()) is True
    assert ann.historical_amount_showable({"annotation_available": False}) is False
    assert ann.historical_amount_showable({}) is False


def test_router_amount_text_withholds_without_a_vouching_annotation() -> None:
    fmt = lambda v: f"${v:.6f}"  # noqa: E731
    vouched = router_cost_disclosure()
    assert ann.router_amount_text(vouched, 0.020806, fmt) == "$0.020806"
    unvouched = {"annotation_available": False, "withheld": "withheld — no annotation"}
    assert ann.router_amount_text(unvouched, 0.020806, fmt) == "withheld — no annotation"
    assert ann.router_amount_text(unvouched, 0.020806, fmt, compact=True) == "withheld"
    # A null amount is withheld even when an annotation is present.
    assert ann.router_amount_text(vouched, None, fmt) == vouched["withheld"]


def test_arena_render_withholds_the_router_amount_when_unvouched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from router.foundry_arena import FleetSlate

    _hide_annotation(monkeypatch)
    report = RouterService().dispatch(
        "POST", "/fleet/run", body=json.dumps({"roles": {}}).encode()
    ).payload["report"]
    cli._print_arena_report(report, FleetSlate())
    out = capsys.readouterr().out
    rows = {
        ln.split()[0]: ln
        for ln in out.splitlines()
        if ln.startswith("  ") and "ms  " in ln and ln.split()[0:1]
    }
    assert "withheld" in rows["router"]
    assert "$" not in rows["router"]
    # Direct-model arms still show their amounts — they were never affected.
    for arm in DIRECT_ARMS:
        assert "$" in rows[arm]
        assert "withheld" not in rows[arm]


def test_foundry_live_withholds_the_amount_when_unvouched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _hide_annotation(monkeypatch)
    assert cli.main(["foundry", "live"]) == 0
    out = capsys.readouterr().out
    cost_line = next(ln for ln in out.splitlines() if "routed cost" in ln)
    avg_line = next(ln for ln in out.splitlines() if "avg $/task" in ln)
    assert "withheld" in cost_line and "$0.02" not in cost_line
    assert "withheld" in avg_line and "$0.0041" not in avg_line


def test_publisher_withholds_the_router_amount_when_unvouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = json.loads(ARENA.read_text(encoding="utf-8"))
    _hide_annotation(monkeypatch)
    report = RouterService().dispatch(
        "POST", "/fleet/run", body=json.dumps({"roles": {}}).encode()
    ).payload["report"]
    totals = report["arm_totals"]
    assert totals["router"]["total_cost_usd"] is None
    assert totals["router"]["cost_withheld"] is True
    for arm in DIRECT_ARMS:
        assert totals[arm]["total_cost_usd"] == source["arm_totals"][arm]["total_cost_usd"]
        assert "cost_withheld" not in totals[arm]
    # Withholding must never write back into the artifact it read.
    assert json.loads(ARENA.read_text(encoding="utf-8")) == source


def test_dashboard_withholds_an_unvouched_router_amount() -> None:
    from router.dashboard import DASHBOARD_HTML

    assert "disc.annotation_available === true" in DASHBOARD_HTML
    assert "cost_withheld === true" in DASHBOARD_HTML
