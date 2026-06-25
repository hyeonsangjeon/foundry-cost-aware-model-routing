"""``python -m policy`` — list the seeded candidate models for each task class."""

from __future__ import annotations

from .schema import TaskClass, load_default_policy


def main() -> int:
    policy = load_default_policy()
    print(f"seed policy v{policy.version} — candidates per class (cheapest-first)")
    for tc in TaskClass:
        print(f"\n{tc.value}:")
        for rank, c in enumerate(policy.candidates_for(tc)):
            print(
                f"  [{rank}] {c.model:<14} "
                f"pass={c.prior_pass:.2f}  $/resolved={c.prior_usd_resolved:.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
