"""Reusable policy operations: human-readable show, contract validation, diff.

Pure functions over :class:`policy.PolicyTable` so the ``cost-router policy``
subcommands, ``python -m policy``, and the eval/regression flows all share one
implementation. Nothing here touches the network or routes traffic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import describe_model
from .schema import PolicyTable, TaskClass, load_default_policy


def show_text(policy: PolicyTable | None = None) -> str:
    """Render a policy as version + cheapest-first candidates per class.

    A trailing "model tiers" legend explains what each generic placeholder model
    stands for (lightweight, reasoning, premium, …) so the identifiers are
    self-describing without referencing any real product name.
    """

    policy = policy or load_default_policy()
    lines = [f"policy v{policy.version} — candidates per class (cheapest-first)"]
    for task_class in TaskClass:
        lines.append(f"\n{task_class.value}:")
        for rank, candidate in enumerate(policy.candidates_for(task_class)):
            lines.append(
                f"  [{rank}] {candidate.model:<14} "
                f"pass={candidate.prior_pass:.2f}  "
                f"$/resolved={candidate.prior_usd_resolved:.2f}"
            )

    seen: dict[str, float] = {}
    for candidates in policy.classes.values():
        for candidate in candidates:
            prior = candidate.prior_usd_resolved
            if candidate.model not in seen or prior < seen[candidate.model]:
                seen[candidate.model] = prior
    lines.append("\nmodel tiers (generic placeholders — not real product names):")
    for model in sorted(seen, key=lambda m: seen[m]):
        meta = describe_model(model)
        lines.append(
            f"  {model:<14} {meta['tier']} · reasoning={meta['reasoning']}\n"
            f"                 {meta['role']}"
        )
    return "\n".join(lines)


def validate_errors(policy: PolicyTable) -> list[str]:
    """Return contract violations for ``policy`` (empty list means valid)."""

    try:
        policy.validate()
    except ValueError as exc:
        return [str(exc)]
    return []


@dataclass(frozen=True)
class PolicyDiff:
    """Per-class candidate/order/prior changes between two policies."""

    version_from: int
    version_to: int
    changes: dict[str, list[str]]

    @property
    def changed(self) -> bool:
        return self.version_from != self.version_to or any(self.changes.values())


def diff_policies(base: PolicyTable, candidate: PolicyTable) -> PolicyDiff:
    """Summarize what changed from ``base`` to ``candidate`` per task class."""

    changes: dict[str, list[str]] = {}
    for task_class in TaskClass:
        base_c = {c.model: c for c in base.classes.get(task_class, ())}
        cand_c = {c.model: c for c in candidate.classes.get(task_class, ())}
        base_order = [c.model for c in base.classes.get(task_class, ())]
        cand_order = [c.model for c in candidate.classes.get(task_class, ())]
        rows: list[str] = []
        for model in cand_order:
            if model not in base_c:
                rows.append(f"+ {model} (added)")
        for model in base_order:
            if model not in cand_c:
                rows.append(f"- {model} (removed)")
        for model in cand_order:
            if model in base_c:
                old, new = base_c[model], cand_c[model]
                deltas = []
                if old.prior_pass != new.prior_pass:
                    deltas.append(f"pass {old.prior_pass:.2f}->{new.prior_pass:.2f}")
                if old.prior_usd_resolved != new.prior_usd_resolved:
                    deltas.append(
                        f"$/res {old.prior_usd_resolved:.2f}->{new.prior_usd_resolved:.2f}"
                    )
                if deltas:
                    rows.append(f"~ {model} ({', '.join(deltas)})")
        if base_order != cand_order:
            rows.append(f"order {base_order} -> {cand_order}")
        if rows:
            changes[task_class.value] = rows
    return PolicyDiff(version_from=base.version, version_to=candidate.version, changes=changes)


def format_diff(diff: PolicyDiff) -> str:
    """Render a :class:`PolicyDiff` as a human-readable block."""

    header = f"policy diff v{diff.version_from} -> v{diff.version_to}"
    if not diff.changed:
        return header + "\n  no changes"
    lines = [header]
    for task_class, rows in diff.changes.items():
        lines.append(f"\n{task_class}:")
        lines.extend(f"  {row}" for row in rows)
    return "\n".join(lines)
