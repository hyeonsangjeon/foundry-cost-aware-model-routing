"""Every deployed model must be priced — enforced, not rediscovered.

03D-3 surfaced `gpt-5.6-terra` unpriced in a paid run's traces. Pinning the 5.6
family closed that instance; diffing the card against the tenant's actual
deployment list then found five more models with no row at all, including a
`DeepSeek-V4-Pro` deployment sitting behind V3.1/V3.2 rows. Both were found by
hand, after the fact, in artifacts nobody reads unless something looks wrong.

This module turns that diff into a test. `tenant-deployments-2026-08-15.yaml` is
a committed control-plane capture; the card must price every chat deployment in
it, and any deliberate omission must carry a written reason. Adding a deployment
without pinning its meter now fails here instead of in a run's cost column.

What this test cannot do — and must not be read as doing — is prove the card is
complete. The Model Router serves from its own managed roster, which is not
enumerable before dispatch: `gpt-5.6-terra` was never deployed on this account
and was served anyway. The deployed set is a lower bound. Offline; no Azure.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from router.rate_card import RateCardV2

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "samples/pricing/foundry-ext-router-2026-08-15.yaml"
DEPLOYMENTS = ROOT / "samples/pricing/tenant-deployments-2026-08-15.yaml"


@pytest.fixture(scope="module")
def card() -> RateCardV2:
    return RateCardV2.from_yaml(CARD)


@pytest.fixture(scope="module")
def capture() -> dict:
    return yaml.safe_load(DEPLOYMENTS.read_text(encoding="utf-8"))


def _by_kind(capture: dict, kind: str) -> list[dict]:
    return [d for d in capture["deployments"] if d["kind"] == kind]


def test_capture_matches_the_card_it_is_checked_against(capture: dict) -> None:
    # A capture from a different account or region would silently pass every
    # coverage assertion below while proving nothing about this card.
    assert capture["account"] == "aoai-foundry-iq-demo-ext"
    assert capture["region"] == "eastus"
    assert capture["captured"] == "2026-08-15"


def test_every_deployed_chat_model_is_priced(card: RateCardV2, capture: dict) -> None:
    unpriced = []
    for dep in _by_kind(capture, "chat"):
        key = card.resolve_pricing_key(dep["model"])
        if key is None or card.rates_for(key) is None:
            unpriced.append(f"{dep['deployment']} -> {dep['model']}")
    assert unpriced == [], (
        "deployed but unpriced (pin the retail meter, or record an "
        f"unpriced_reason in the capture): {unpriced}"
    )


def test_deployment_names_resolve_too_not_just_catalog_ids(card: RateCardV2, capture: dict) -> None:
    # A run configures an arm by *deployment* name, and some deployments differ
    # in case or shape from the catalog model id (kimi-k2-6 vs Kimi-K2.6). If
    # only the catalog form resolved, the alias map would look complete while
    # the string an operator actually types failed closed.
    for dep in _by_kind(capture, "chat"):
        assert card.resolve_pricing_key(dep["deployment"]) is not None, (
            f"deployment name {dep['deployment']!r} does not resolve to a pricing key"
        )


def test_router_deployments_are_not_expected_to_have_a_rate_row(
    card: RateCardV2, capture: dict
) -> None:
    # `model-router` is priced compositely — markup plus whatever it resolved to
    # — so a rate row named after it would be the exact placeholder-pricing bug
    # the v2 card exists to prevent.
    routers = _by_kind(capture, "router")
    assert routers, "the capture should still describe the router deployments"
    for dep in routers:
        assert card.rates_for(dep["model"]) is None


def test_a_deliberate_omission_must_carry_a_written_reason(card: RateCardV2, capture: dict) -> None:
    # Silence is the failure mode this whole change is about. Anything deployed
    # and not priced has to say why, in the capture, in words.
    for dep in capture["deployments"]:
        if dep["kind"] in {"chat", "router"}:
            continue
        key = card.resolve_pricing_key(dep["model"])
        if key is not None and card.rates_for(key) is not None:
            continue
        reason = (dep.get("unpriced_reason") or "").strip()
        assert len(reason) > 20, f"{dep['deployment']} is unpriced with no stated reason"


def test_the_embedding_deployment_is_the_only_unpriced_one(card: RateCardV2, capture: dict) -> None:
    def priced(model: str) -> bool:
        key = card.resolve_pricing_key(model)
        return key is not None and card.rates_for(key) is not None

    unpriced = [
        d["deployment"]
        for d in capture["deployments"]
        if d["kind"] != "router" and not priced(d["model"])
    ]
    assert unpriced == ["text-embedding-3-large"]


def test_deepseek_deployed_version_is_the_one_priced(card: RateCardV2, capture: dict) -> None:
    # The specific trap this test was written for: the card pinned DeepSeek
    # V3.1 and V3.2 for months while the deployed model was V4-Pro. A family
    # name matching is not the same as the deployed model being priced.
    deployed = next(d for d in capture["deployments"] if d["deployment"] == "deepseek-v4-pro")
    assert deployed["model"] == "DeepSeek-V4-Pro"
    assert card.rates_for("DeepSeek-V4-Pro") is not None


def test_coverage_is_a_lower_bound_not_a_completeness_proof(card: RateCardV2) -> None:
    # gpt-5.6-terra is priced here and appears in no deployment list — it was
    # served by the router anyway. Keeping it pinned is what stops this suite
    # from being read as "every deployment covered == every charge covered".
    assert card.rates_for("gpt-5.6-terra") is not None
