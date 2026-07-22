#!/usr/bin/env python3
"""Seal the captured live-arena run into a durable, verifiable measured ledger.

Experiment 10 turns experiment 09's *measured* evidence into a canonical audit
artifact. The real per-call token ``usage`` was already captured live from the
Azure AI Foundry Model Router (keyless Entra) and committed as
``samples/responses/foundry-arena-measured.json``. This script does **not** make
any network call — it re-seals that already-measured usage into the canonical,
hash-chained :class:`~router.ledger.measured.MeasuredJsonlLedger` form so anyone
can independently verify it with ``cost-router ledger measured-replay``.

The output is byte-deterministic: ``captured_at`` is pinned to the artifact's own
capture timestamp, so regenerating always reproduces the committed sample. That
lets a test guard the committed ledger and this generator staying in sync.

Reproduce (offline, no spend)::

    python scripts/build_measured_ledger_sample.py

Regenerate live instead (real keyless calls, then a real ledger)::

    cost-router foundry arena --live --max-output-tokens 3000 \
      --pricing samples/pricing/foundry-5series.yaml \
      --ledger  samples/ledger/arena-measured.ledger.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from router.ledger.measured import (  # noqa: E402
    MeasuredJsonlLedger,
    MeasuredLedgerRecord,
    MeasuredReplayReport,
    verify_measured_ledger,
)
from router.pricing import PricingTable  # noqa: E402

ARTIFACT = REPO_ROOT / "samples" / "responses" / "foundry-arena-measured.json"
PRICING = REPO_ROOT / "samples" / "pricing" / "foundry-5series.yaml"
SAMPLE = REPO_ROOT / "samples" / "ledger" / "arena-measured.ledger.jsonl"


def build_measured_ledger(
    *,
    artifact: Path = ARTIFACT,
    pricing_path: Path = PRICING,
    out_path: Path = SAMPLE,
) -> MeasuredReplayReport:
    """Rebuild the durable measured ledger from the captured arena artifact.

    Deterministic: ``out_path`` is rewritten from scratch and every row is sealed
    with the artifact's own ``captured_at``, so the bytes are reproducible.
    """

    report = json.loads(artifact.read_text(encoding="utf-8"))
    pricing = PricingTable.from_yaml(pricing_path)
    captured_at = str(report["captured_at"])

    records = [
        MeasuredLedgerRecord.build(outcome, pricing=pricing, captured_at=captured_at)
        for outcome in report["results"]
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    MeasuredJsonlLedger(out_path).append_many(records)

    return verify_measured_ledger(out_path)


def main() -> int:
    verified = build_measured_ledger()
    print(f"wrote {SAMPLE.relative_to(REPO_ROOT)}")
    print(f"records: {verified.records}  replayed: {verified.replayed}")
    print(f"hash-chain + cost-replay: {'PASS' if verified.ok else 'FAIL'}")
    return 0 if verified.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
