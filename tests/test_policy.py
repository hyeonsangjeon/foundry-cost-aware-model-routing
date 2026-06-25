"""Schema validation and ordering-invariant tests for the policy table."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy import Candidate, PolicyTable, TaskClass, load_default_policy
from policy.schema import DEFAULT_POLICY_PATH


def test_seed_policy_loads_and_validates() -> None:
    policy = load_default_policy()
    assert policy.version >= 1


def test_all_task_classes_present() -> None:
    policy = load_default_policy()
    assert set(policy.classes.keys()) == set(TaskClass)
    for tc in TaskClass:
        assert len(policy.candidates_for(tc)) >= 1


def test_candidate_priors_within_contract() -> None:
    policy = load_default_policy()
    for tc in TaskClass:
        for c in policy.candidates_for(tc):
            assert c.model.strip()
            assert 0.0 <= c.prior_pass <= 1.0
            assert c.prior_usd_resolved > 0.0


def test_candidates_are_cheapest_first() -> None:
    policy = load_default_policy()
    for tc in TaskClass:
        costs = [c.prior_usd_resolved for c in policy.candidates_for(tc)]
        assert costs == sorted(costs), f"{tc.value} not cheapest-first: {costs}"


def test_no_duplicate_models_per_class() -> None:
    policy = load_default_policy()
    for tc in TaskClass:
        models = [c.model for c in policy.candidates_for(tc)]
        assert len(models) == len(set(models))


def test_candidates_for_accepts_string_and_enum() -> None:
    policy = load_default_policy()
    assert policy.candidates_for("generate") == policy.candidates_for(TaskClass.GENERATE)


@pytest.mark.parametrize(
    "model,prior_pass,usd",
    [
        ("x", 1.5, 0.10),   # prior_pass out of range
        ("x", -0.1, 0.10),  # prior_pass out of range
        ("x", 0.5, 0.0),    # non-positive cost
        ("", 0.5, 0.10),    # empty model
    ],
)
def test_candidate_rejects_bad_values(model: str, prior_pass: float, usd: float) -> None:
    with pytest.raises(ValueError):
        Candidate(model=model, prior_pass=prior_pass, prior_usd_resolved=usd)


def test_unknown_task_class_raises() -> None:
    with pytest.raises(ValueError):
        TaskClass.from_str("refactor")


def test_validate_rejects_unsorted_candidates() -> None:
    bad = PolicyTable(
        classes={
            TaskClass.PLAN: (
                Candidate("a", 0.60, 2.00),
                Candidate("b", 0.70, 1.00),  # cheaper after pricier -> violates ordering
            )
        }
    )
    with pytest.raises(ValueError):
        bad.validate()


def test_validate_rejects_missing_classes() -> None:
    partial = PolicyTable(classes={TaskClass.PLAN: (Candidate("a", 0.6, 1.0),)})
    with pytest.raises(ValueError):
        partial.validate()


def test_from_dict_round_trips() -> None:
    data = {
        "version": 2,
        "classes": {
            tc.value: [
                {"model": f"{tc.value}-m{i}", "prior_pass": 0.5, "prior_usd_resolved": float(i + 1)}
                for i in range(2)
            ]
            for tc in TaskClass
        },
    }
    policy = PolicyTable.from_dict(data).validate()
    assert policy.version == 2
    assert set(policy.classes.keys()) == set(TaskClass)


def test_default_policy_path_exists() -> None:
    assert Path(DEFAULT_POLICY_PATH).is_file()
