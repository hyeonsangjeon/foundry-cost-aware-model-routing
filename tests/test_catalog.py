"""Tests for the placeholder model catalog and its surfacing in policy views."""

from __future__ import annotations

from policy import MODEL_CATALOG, describe_model, load_default_policy
from policy.ops import show_text
from router.pipeline import policy_summary

PLACEHOLDER_MODELS = {
    "mini-fast",
    "swift-coder",
    "balanced-pro",
    "deep-reasoner",
    "premium-max",
}


def test_catalog_covers_every_seed_model() -> None:
    used = {c.model for cands in load_default_policy().classes.values() for c in cands}
    assert used == PLACEHOLDER_MODELS
    assert used <= set(MODEL_CATALOG)


def test_describe_model_returns_generic_fields() -> None:
    for model in PLACEHOLDER_MODELS:
        meta = describe_model(model)
        assert meta["model"] == model
        assert meta["tier"] and meta["role"] and meta["reasoning"]


def test_describe_model_falls_back_for_unknown() -> None:
    meta = describe_model("some-custom-model")
    assert meta["model"] == "some-custom-model"
    assert meta["tier"] == "Custom"
    assert "no catalog description" in meta["role"].lower()


def test_catalog_has_no_vendor_or_reference_wording() -> None:
    blob = " ".join(
        f"{m} {e['tier']} {e['reasoning']} {e['role']}" for m, e in MODEL_CATALOG.items()
    ).lower()
    for banned in (
        "openai",
        "anthropic",
        "azure",
        "gpt",
        "claude",
        "gemini",
        "llama",
        "mistral",
        "foundry",
        "http",
    ):
        assert banned not in blob


def test_policy_summary_enriches_candidates_and_catalog() -> None:
    summary = policy_summary()
    catalog = summary["catalog"]
    # Catalog is cheapest-first and one entry per distinct model.
    assert [c["model"] for c in catalog] == [
        "mini-fast",
        "swift-coder",
        "balanced-pro",
        "deep-reasoner",
        "premium-max",
    ]
    assert all({"model", "tier", "reasoning", "role"} <= set(c) for c in catalog)
    # Every candidate row carries its tier/role too.
    generate = summary["classes"]["generate"]
    assert all("tier" in cand and "role" in cand for cand in generate)


def test_show_text_appends_tier_legend() -> None:
    text = show_text()
    assert "model tiers" in text
    assert "Lightweight" in text
    assert "Premium frontier" in text
    for model in PLACEHOLDER_MODELS:
        assert model in text
