"""Human-readable descriptions for the generic placeholder model tiers.

The routing policy references models by generic placeholder identifiers
(``mini-fast``, ``deep-reasoner``, …) rather than any real vendor or product
name. This module attaches a short, capability-based description to each tier so
a reviewer can understand *what a placeholder stands for* in a cost-aware routing
setup — a lightweight high-volume tier, a deliberate reasoning tier, and so on —
without introducing any real model name.

Every string here is an illustrative, vendor-neutral role description, not a
claim about a specific product. ``describe_model`` degrades gracefully for
identifiers that are not in the catalog so custom policies never break.
"""

from __future__ import annotations

MODEL_CATALOG: dict[str, dict[str, str]] = {
    "mini-fast": {
        "tier": "Lightweight",
        "reasoning": "minimal",
        "role": (
            "Cheapest, lowest-latency tier. Handles simple, high-volume work "
            "(short generation, quick validation) where deep reasoning is not needed."
        ),
    },
    "swift-coder": {
        "tier": "Efficient coder",
        "reasoning": "light",
        "role": (
            "Low-cost, code-specialized tier. Good default for straightforward code "
            "generation and small edits before escalating to a pricier model."
        ),
    },
    "balanced-pro": {
        "tier": "Balanced",
        "reasoning": "moderate",
        "role": (
            "General-purpose mid tier. The everyday quality/cost trade-off used when "
            "the lightweight tier is not reliable enough."
        ),
    },
    "deep-reasoner": {
        "tier": "Reasoning",
        "reasoning": "high",
        "role": (
            "Higher-cost tier for deliberate, multi-step reasoning on hard planning or "
            "repository-patch tasks where correctness matters more than price."
        ),
    },
    "premium-max": {
        "tier": "Premium frontier",
        "reasoning": "maximum",
        "role": (
            "Maximum-capability ceiling and the most expensive tier. Reserved for the "
            "hardest tasks whose value clearly justifies the extra spend."
        ),
    },
}

_FALLBACK = {
    "tier": "Custom",
    "reasoning": "unspecified",
    "role": "Custom policy tier — no catalog description available for this identifier.",
}


def describe_model(model: str) -> dict[str, str]:
    """Return ``{tier, reasoning, role}`` for a placeholder model identifier.

    Unknown identifiers get a neutral fallback so custom policies still render.
    """

    entry = MODEL_CATALOG.get(model)
    if entry is None:
        return {"model": model, **_FALLBACK}
    return {"model": model, **entry}
