"""Every field the run plan hashes should have a consumer — or a written reason.

``plan_hash`` is computed over the whole ``execution`` mapping, so anything put
in there changes the hash of every config that carries it and therefore forces a
fresh human approval. That price is worth paying for a field the run actually
reads. It is not worth paying for a field nothing reads: such a field reads like
a control — in the approval view, in a preregistration, in a lab-notebook page —
while changing nothing about what is dispatched.

This module pins the fields that are in that state today, each with the reason
it has no reader. It is a tripwire, not a cleanup order: the existing entries are
recorded, not scheduled. The test fails when a *new* reader-less field appears,
and equally when a pinned one gains a reader — delete its entry then, because a
stale entry is a false claim about the code.

``seed.random_seed`` is why this file exists. Three preregistrations described
their runs as using a "fixed seed", and no seed has ever reached a model API; the
value's only effect is that it salts ``plan_hash``. See the errata sections of
``benchmarks/original-coding/prereg-03d-router-modes.md``,
``prereg-03d2-router-modes.md``, and ``prereg-03d3-router-modes.md``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from router.run_plan import LocalRunConfig, resolve_run_plan

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "foundry.example.yaml"
SMOKE_WORKLOAD = "samples/workloads/validated-smoke.example.jsonl"

#: The resolver. Skipped by the reader sweep because nearly everything it does
#: with these key names is *building* the plan — reading the raw YAML, or filling
#: a mapping it just constructed. Its genuine reads of a finished plan are listed
#: in :data:`CONSUMED_INSIDE_THE_RESOLVER` instead, and pinned by a test.
RESOLVER = ROOT / "src" / "router" / "run_plan.py"

#: Dotted ``execution`` paths with no reader on the execution path, and why.
#: ``[]`` marks a list element (``arms[]`` is "each entry of ``arms``").
READER_LESS_EXECUTION_FIELDS: dict[str, str] = {
    "arms[].direct_model_evidence": (
        "Operator-supplied note about how a direct arm's model was confirmed; it is "
        "copied into the plan as provenance and never consulted when dispatching."
    ),
    "arms[].expected.format": (
        "Declares the shape of the expected-deployment assertion. The doctor compares "
        "routing_mode for router arms and name/version for direct ones, never format."
    ),
    "arms[].expected.payload_hash_or_etag": (
        "Per-arm digest of the deployment properties the operator saw. The doctor "
        "re-reads the live properties instead of comparing against this digest."
    ),
    "artifacts.publish_sanitized": (
        "Declares an intent to publish a sanitized bundle; the sanitizing path is "
        "driven by explicit CLI subcommands, which never consult this flag."
    ),
    "budget.smoke_ceiling_usd": (
        "Second copy of the smoke ceiling. The copy that is read lives at "
        "pricing.smoke_authorization_ceiling_usd; this one is display provenance."
    ),
    "deployment_evidence.exported_arm_payload": (
        "Path to the management-plane export the operator captured; evidence that "
        "the capture happened, not an input the runner opens."
    ),
    "deployment_evidence.management_api_version": (
        "Records which management API version produced the deployment evidence. "
        "The runner never calls the management plane, so nothing reads it."
    ),
    "deployment_evidence.payload_hash_or_etag": (
        "Digest of that captured export, so a reader can tell whether the evidence "
        "changed between runs. Nothing recomputes or compares it automatically."
    ),
    "endpoint.inference": (
        "Redacted copy of the model-inference endpoint for the approval view. The "
        "live client resolves its own from FoundryConfig.resolved_inference_endpoint."
    ),
    "estimand.analysis_unit": (
        "Part of the analysis contract. The whole estimand block is hashed so the "
        "analysis is bound to the approved plan; scoring is done against the "
        "preregistration by hand, and the runner never branches on any of it."
    ),
    "estimand.cost_per_pass_formula": (
        "Same contract, same reason: it fixes how cost-per-pass is to be computed "
        "for whoever scores the run, and no code computes it from this string."
    ),
    "estimand.denominator_policy": (
        "Same contract, same reason: it fixes what the denominator counts, and "
        "coverage is computed from the recorded cells rather than from this field."
    ),
    "estimand.failure_policy": (
        "Same contract, same reason: it fixes how a failed cell scores, and the "
        "grader records the outcome without consulting the declared policy."
    ),
    "estimand.paired_statistic": (
        "Same contract, same reason: it names the test to use when comparing arms, "
        "and no statistic is run inside this repository."
    ),
    "estimand.repeat_aggregation": (
        "Same contract, same reason: it fixes how repeats collapse to one number, "
        "and the runner stores every repeat rather than aggregating them."
    ),
    "preregistration.blob": (
        "The git blob the plan pins for the preregistration. verify_unmodified() "
        "exists to compare it against the file on disk but is called from nowhere "
        "outside its own tests; the enforced check is the commit timestamp."
    ),
    "pricing.pricing_basis": (
        "Records whether the rate card prices per-token or per-1K. The pricing "
        "engine reads the basis off the rate card itself, not off the plan."
    ),
    "privacy.retain_raw_prompts": (
        "Declares prompt retention. Only retain_raw_outputs is read (the doctor "
        "view); prompts are governed by the sealed-snapshot path regardless."
    ),
    "privacy.retain_raw_response_ids": (
        "Declares response-id retention, with the same gap as retain_raw_prompts: "
        "recorded in the plan, not consulted by the writer that seals a run."
    ),
    "retry.provider_internal_retries_disabled": (
        "Hard-coded True. It asserts that the SDK's own retry loop is off so that "
        "attempt counts stay honest; it is a declaration, never a switch."
    ),
    "seed.order_policy": (
        "The string 'task-major, then repeat, then arm; deterministic'. It describes "
        "the loop in measure.py; the loop is hard-coded and does not read it back."
    ),
    "seed.random_seed": (
        "No seed reaches any model API — neither request surface in foundry_live.py "
        "sends one, and no measured code path uses randomness. Its only effect is "
        "that it sits in execution, so it salts plan_hash."
    ),
}

#: Fields whose only genuine consumer lives inside the skipped resolver module.
#: Values are the expression the consumer uses, and a test pins that each one is
#: still literally present — so the exemption cannot outlive the code it names.
CONSUMED_INSIDE_THE_RESOLVER: dict[str, str] = {
    "execution_shape.repetitions": 'int(self.execution["execution_shape"]["repetitions"])',
    "retry.max_retries": 'RetryPolicy(max_retries=int(plan.execution["retry"]["max_retries"]))',
}


def _read_sites(key: str) -> list[str]:
    """Every ``x["key"]`` / ``x.get("key")`` site under ``src/``, minus the resolver.

    A dict *literal* key (``"key": value``) deliberately does not match: that is a
    write. Only subscript and ``.get`` reads count.
    """

    pattern = re.compile(
        r"""\[\s*["']{k}["']\s*\]|\.get\(\s*["']{k}["']""".format(k=re.escape(key))
    )
    sites: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if path == RESOLVER:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                sites.append(f"{path.relative_to(ROOT)}:{lineno}")
    return sites


def _leaf_paths(node: Any, prefix: str = "") -> set[str]:
    """Flatten a mapping to dotted leaf paths; list elements collapse to ``name[]``."""

    if isinstance(node, dict):
        out: set[str] = set()
        for key, value in node.items():
            out |= _leaf_paths(value, f"{prefix}.{key}" if prefix else key)
        return out
    if isinstance(node, list):
        out = set()
        for value in node:
            out |= _leaf_paths(value, f"{prefix}[]")
        return out
    return {prefix}


def _rate_card(tmp_path: Path) -> None:
    (tmp_path / "tenant-rates.yaml").write_text(
        "version: 7\n"
        "currency: USD\n"
        "source: acme-tenant\n"
        "effective_date: 2026-08-01\n"
        "pricing_basis: composite\n"
        "models:\n"
        "  model-router: {input: 3.0, cached: 1.5, output: 10.0, reasoning: 10.0}\n"
        "  premium-max: {input: 5.0, cached: 2.5, output: 15.0, reasoning: 15.0}\n"
        "default: {input: 1.0, cached: 0.5, output: 2.0, reasoning: 2.0}\n",
        encoding="utf-8",
    )


def _fully_populated_execution(tmp_path: Path) -> dict[str, Any]:
    """A benchmark plan with every optional block filled in.

    The shipped template leaves ``estimand`` and ``preregistration`` unset, which
    would hide their fields from the sweep entirely. This config fills them, and
    the union of the two plans is what gets swept.
    """

    _rate_card(tmp_path)
    mapping: dict[str, Any] = {
        "schema_version": 1,
        "template": False,
        "run_mode": "benchmark",
        "foundry": {
            "auth": "entra",
            "endpoint_kind": "azure_openai",
            "azure_openai_endpoint": "https://acme-res.example.com/",
            "model_inference_endpoint": "https://acme-res.services.ai.example.com/",
            "api_version": "2024-10-21",
        },
        "arms": [
            {
                "id": "router-cost",
                "kind": "model_router",
                "provider": "openai",
                "requested_model": "model-router",
                "deployment": "model-router",
                "expected": {"format": "router", "name": "cost", "version": "2025-01"},
            },
            {
                "id": "direct-premium",
                "kind": "direct",
                "provider": "openai",
                "requested_model": "premium-max",
                "deployment": "premium-max",
                "direct_model_evidence": "portal screenshot 2026-08-01",
            },
        ],
        "deployment_evidence": {
            "management_resource_id": "/subscriptions/x/resourceGroups/y",
            "management_api_version": "2024-10-01",
            "exported_arm_payload": "evidence/arm-export.json",
            "payload_hash_or_etag": "sha256:deadbeef",
            "captured_at": "2026-08-01T00:00:00Z",
        },
        "benchmark": {
            "workload": str(ROOT / SMOKE_WORKLOAD),
            "rate_card": "tenant-rates.yaml",
            "smoke_authorization_ceiling_usd": None,
            "repetitions": 2,
            "max_output_tokens": 256,
            "budget_usd": 5.0,
            "random_seed": 7,
            "estimand": {
                "analysis_unit": "task",
                "repeat_aggregation": "mean",
                "denominator_policy": "all-attempted",
                "failure_policy": "count-as-zero",
                "cost_per_pass_formula": "total_cost / passes",
                "paired_statistic": "wilcoxon",
            },
            "grader": {"kind": "exec-signals", "version": 1},
            "retry": {"max_retries": 3},
            "preregistration": {
                "path": "benchmarks/original-coding/prereg-03d3-router-modes.md",
                "blob": "8584e1f8c6031d7be6b03d01a9e292c83d57bab5",
                "commit": "454c8159e6e3666a6b24982ef30766ea73059f22",
            },
        },
        "privacy": {
            "retain_raw_prompts": True,
            "retain_raw_outputs": True,
            "retain_raw_response_ids": True,
        },
        "artifacts": {"local_root": "results/local", "publish_sanitized": True},
        "display": {"locale": "en"},
    }
    config = LocalRunConfig.from_mapping(
        mapping, base_dir=tmp_path, source=str(tmp_path / ".foundry.local.yaml")
    )
    return resolve_run_plan(config, env={}).execution


def _swept_leaf_paths(tmp_path: Path) -> set[str]:
    return _leaf_paths(_fully_populated_execution(tmp_path))


def _reader_less(tmp_path: Path) -> set[str]:
    return {
        path
        for path in _swept_leaf_paths(tmp_path)
        if path not in CONSUMED_INSIDE_THE_RESOLVER
        and not _read_sites(path.split(".")[-1].replace("[]", ""))
    }


def test_reader_less_execution_fields_match_the_pinned_list(tmp_path: Path) -> None:
    """The tripwire. A new hashed-but-unread field has to be declared here first."""

    found = _reader_less(tmp_path)
    pinned = set(READER_LESS_EXECUTION_FIELDS)

    new = sorted(found - pinned)
    assert not new, (
        "these execution fields are hashed into plan_hash but nothing reads them: "
        f"{new}. Either give the field a reader, or add it to "
        "READER_LESS_EXECUTION_FIELDS with a one-line reason. A field nobody reads "
        "still forces a re-approval on every change, and still reads like a control "
        "to anyone looking at the approval view."
    )

    gained = sorted(pinned - found)
    assert not gained, (
        f"these fields now have a reader and must be dropped from the pinned list: "
        f"{gained}. Leaving them listed would state something false about the code."
    )


def test_every_pinned_field_carries_a_reason(tmp_path: Path) -> None:
    """No silent entries: an exemption without a stated reason is not an exemption."""

    for path, reason in READER_LESS_EXECUTION_FIELDS.items():
        assert reason.strip(), f"{path} is pinned with no reason"
        assert len(reason.split()) >= 8, f"{path}: reason is too thin to be useful"


def test_the_sweep_sees_every_execution_block(tmp_path: Path) -> None:
    """Guards the sweep itself: an empty block would hide its fields from the check."""

    execution = _fully_populated_execution(tmp_path)
    empty = sorted(k for k, v in execution.items() if v is None or v == {} or v == [])
    assert not empty, (
        f"{empty} resolved empty, so any reader-less field inside is invisible to "
        "this test. Populate it in _fully_populated_execution."
    )


def test_the_sweep_covers_the_shipped_template(tmp_path: Path) -> None:
    """The swept config must be a structural superset of what a fresh clone resolves.

    The template leaves ``estimand`` and ``preregistration`` unset, so it resolves
    *fewer* leaves — but it must never resolve one the populated config lacks, or
    the sweep would have a blind spot that ships to every new user.
    """

    populated = _swept_leaf_paths(tmp_path)
    template = _leaf_paths(resolve_run_plan(LocalRunConfig.from_yaml(TEMPLATE), env={}).execution)
    missed = sorted(
        path
        for path in template
        if path not in populated and not any(p.startswith(path + ".") for p in populated)
    )
    assert not missed, (
        f"{TEMPLATE.name} resolves {missed}, which _fully_populated_execution does "
        "not cover, so those fields are never swept for readers."
    )


def test_resolver_internal_consumers_still_exist() -> None:
    """The two in-resolver exemptions must keep naming code that is really there."""

    source = RESOLVER.read_text(encoding="utf-8")
    for path, expression in CONSUMED_INSIDE_THE_RESOLVER.items():
        assert expression in source, (
            f"{path} is exempted because {RESOLVER.name} contains {expression!r}, "
            "which it no longer does. Re-check whether the field still has a reader."
        )


def test_random_seed_never_reaches_a_request_surface() -> None:
    """The specific claim the errata rests on, pinned so it cannot regress quietly."""

    live = (ROOT / "src" / "router" / "foundry_live.py").read_text(encoding="utf-8")
    assert '"seed"' not in live and "seed=" not in live

    measured = [
        ROOT / "src" / "router" / "measure.py",
        ROOT / "src" / "router" / "foundry_live.py",
    ]
    for path in measured:
        text = path.read_text(encoding="utf-8")
        assert "random_seed" not in text, (
            f"{path.name} now mentions random_seed. If it became a real input, "
            "update READER_LESS_EXECUTION_FIELDS and the prereg errata that say "
            "no seed reaches the model API."
        )
