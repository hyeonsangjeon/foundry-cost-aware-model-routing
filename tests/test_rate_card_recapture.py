"""The 2026-08-15 rate-card re-capture: the 5.6 family, pinned whole.

03D-3 measured something the card had not anticipated. The balanced
`model-router` deployment answered 12 of its 72 calls with `gpt-5.6-terra` — a
model that is in no version of the 27-model candidate pool and has never been
deployed on this account. The card had no row for it, so `pricing_key` resolved
to ``None``, all 12 calls failed closed, and that arm's cost came out
incomplete. The gap was in our enumeration, not in Azure: the Retail Prices API
has published terra and luna meters since 2026-07-01.

The fix could not be an in-place edit. `_resolve_pricing` folds the card's full
text into `plan_hash`, and two sealed preregistrations bind the 2026-08-05
card's exact sha256 — so a single byte would have invalidated them
retroactively. The re-capture is therefore a new dated file, and the tests below
pin both halves of that contract:

* the 2026-08-05 card is frozen at the bytes the preregs sealed;
* the 2026-08-15 card differs from it only by *adding* rows — no rate moved,
  which is what makes it a re-capture and not a price update.

A second pass widened the scope again: diffing the card against the tenant's
actual deployment list found five more models with no row at all, including a
`DeepSeek-V4-Pro` deployment behind V3.1/V3.2 rows. Coverage of the deployed set
is enforced separately in ``test_deployed_set_coverage``; what is pinned here is
that the widening never repriced anything that was already there.

Everything here is offline: two YAML files, a hash, and arithmetic.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path

import pytest

from router.rate_card import RateCardV2

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "samples/pricing/foundry-ext-router.yaml"
RECAPTURE = ROOT / "samples/pricing/foundry-ext-router-2026-08-15.yaml"
PREREGS = (
    ROOT / "benchmarks/original-coding/prereg-03d2-router-modes.md",
    ROOT / "benchmarks/original-coding/prereg-03d3-router-modes.md",
)

#: The sha256 sealed by prereg-03d2 and prereg-03d3. This constant may never be
#: updated to match a changed file — that is the whole point of a seal.
SEALED_CARD_SHA256 = "ff6f5378e14d4e78fa50488c6e0dafa7564dbe0293dcc9e6ea9b4411946919c3"

#: The two siblings of the deployed `gpt-5.6-sol` that the 2026-08-05 pass
#: missed. terra was actually served; luna never has been.
FAMILY_KEYS = {"gpt-5.6-terra", "gpt-5.6-luna"}

#: Deployments on this account that no version of the card had ever priced,
#: found by diffing it against the control-plane capture. Note DeepSeek-V4-Pro:
#: the card pinned V3.1 and V3.2 while the *deployed* model was V4-Pro.
DEPLOYED_SURFACE_KEYS = {
    "DeepSeek-V4-Pro",
    "Kimi-K2.6",
    "Mistral-Large-3",
    "Cohere-command-a-plus-05-2026",
    "Phi-4-reasoning",
}

ADDED_KEYS = FAMILY_KEYS | DEPLOYED_SURFACE_KEYS

#: Token totals summed over the 12 unpriced `gpt-5.6-terra` cells of the 03D-3
#: live run (results/local/03d/run/20260814T141510Z/traces.jsonl). Reasoning
#: tokens are non-zero, which is why terra's reasoning rate is exercised rather
#: than assumed.
TERRA_03D3_USAGE = {"input": 2130, "cached": 0, "output": 1004, "reasoning": 96}


@pytest.fixture(scope="module")
def frozen() -> RateCardV2:
    return RateCardV2.from_yaml(FROZEN)


@pytest.fixture(scope="module")
def recapture() -> RateCardV2:
    return RateCardV2.from_yaml(RECAPTURE)


# --------------------------------------------------------------------------- #
# The seal: the 2026-08-05 card is frozen at the bytes two preregs bound
# --------------------------------------------------------------------------- #


def test_sealed_preregs_still_bind_the_frozen_cards_actual_bytes() -> None:
    digest = hashlib.sha256(FROZEN.read_bytes()).hexdigest()
    assert digest == SEALED_CARD_SHA256

    for prereg in PREREGS:
        text = prereg.read_text(encoding="utf-8")
        sealed = re.search(r"^rate_card_hash:\s*sha256:([0-9a-f]{64})", text, re.MULTILINE)
        path = re.search(r"^rate_card_path:\s*(\S+)", text, re.MULTILINE)
        assert sealed and path, f"{prereg.name} no longer pins a rate card"
        # Both the hash and the path it names must still describe the frozen
        # file — repointing a sealed prereg at the new card would be the same
        # violation as editing the old one.
        assert sealed.group(1) == digest, f"{prereg.name} seal no longer matches the card"
        assert (ROOT / path.group(1)).resolve() == FROZEN.resolve()


def test_recapture_is_a_separate_file_and_does_not_replace_the_frozen_one() -> None:
    assert FROZEN.is_file() and RECAPTURE.is_file()
    assert FROZEN.read_bytes() != RECAPTURE.read_bytes()


# --------------------------------------------------------------------------- #
# The re-capture: two rows added, nothing repriced
# --------------------------------------------------------------------------- #


def test_recapture_adds_the_missing_siblings_and_moves_no_rate(
    frozen: RateCardV2, recapture: RateCardV2
) -> None:
    assert set(recapture.rates) - set(frozen.rates) == ADDED_KEYS
    assert set(frozen.rates) - set(recapture.rates) == set()  # nothing dropped
    # Every carried-over row is byte-for-byte the same rate. If a price had
    # genuinely moved this test *should* fail — it would no longer be a
    # re-capture, and the header's "no rate moved" claim would be false.
    repriced = {k for k in frozen.rates if frozen.rates[k] != recapture.rates[k]}
    assert repriced == set()
    assert recapture.router_input_markup == frozen.router_input_markup


def test_recapture_carries_the_dated_aliases_for_the_new_rows(
    frozen: RateCardV2, recapture: RateCardV2
) -> None:
    added = {k: v for k, v in recapture.alias_map.items() if k not in frozen.alias_map}
    # Every new alias must land on a row that exists — an alias pointing at a
    # missing key resolves to a pricing_key that then fails to price, which is
    # harder to diagnose than no alias at all.
    assert set(added.values()) <= set(recapture.rates)
    assert added["gpt-5.6-terra-2026-07-09"] == "gpt-5.6-terra"
    assert added["gpt-5.6-luna-2026-07-09"] == "gpt-5.6-luna"
    # No alias was added for a key the card does not actually price.
    assert set(added.values()) == ADDED_KEYS
    # The pre-existing alias map is untouched, exactly as the rates are.
    assert all(recapture.alias_map[k] == v for k, v in frozen.alias_map.items())


def test_recapture_is_stamped_as_a_single_2026_08_15_snapshot(recapture: RateCardV2) -> None:
    assert recapture.capture_date == "2026-08-15"
    assert recapture.effective_date == "2026-08-15"
    # The re-capture inherits the card's identity, not just its numbers.
    assert recapture.schema_version == 2
    assert recapture.currency == "USD"
    assert recapture.unit_basis == "per_1m_tokens"
    assert recapture.region == "eastus"


# --------------------------------------------------------------------------- #
# The gap itself: what 03D-3 could not price, the re-capture can
# --------------------------------------------------------------------------- #


def test_frozen_card_reproduces_the_03d3_fail_closed_gap(frozen: RateCardV2) -> None:
    # This is not a regression to fix — it is the sealed card's real behavior,
    # pinned so the re-capture has something to be measured against.
    assert frozen.resolve_pricing_key("gpt-5.6-terra") is None
    breakdown = frozen.composite_cost(
        TERRA_03D3_USAGE, pricing_key=None, include_router_markup=True
    )
    assert breakdown.priced is False
    assert "no pinned rate" in (breakdown.reason or "")
    # Fail-closed means the amount is withheld, never a fabricated zero-cost win.
    assert breakdown.total_usd == Decimal("0")


def test_recapture_prices_the_terra_cells_03d3_left_unpriced(recapture: RateCardV2) -> None:
    key = recapture.resolve_pricing_key("gpt-5.6-terra")
    assert key == "gpt-5.6-terra"
    breakdown = recapture.composite_cost(
        TERRA_03D3_USAGE, pricing_key=key, include_router_markup=True
    )
    assert breakdown.priced is True
    # Long-context tier (the conservative one the card stores), plus the router
    # markup — these calls came through a `model-router` deployment.
    assert breakdown.input_usd == Decimal("2130") * Decimal("5.0") / Decimal("1000000")
    assert breakdown.output_usd == Decimal("1004") * Decimal("22.5") / Decimal("1000000")
    assert breakdown.reasoning_usd == Decimal("96") * Decimal("22.5") / Decimal("1000000")
    assert breakdown.router_markup_usd == Decimal("2130") * Decimal("0.14") / Decimal("1000000")
    assert breakdown.total_usd == Decimal("0.0356982")


def test_terra_reasoning_is_priced_at_the_output_rate_not_dropped(
    recapture: RateCardV2,
) -> None:
    # The 96 observed reasoning tokens are the reason this matters: with
    # reasoning left null the card would fail closed on every terra call and the
    # arm would stay cost-incomplete even with input/output pinned.
    rates = recapture.rates_for("gpt-5.6-terra")
    assert rates is not None and rates.reasoning == rates.output


def test_luna_is_pinned_from_its_meter_even_though_it_was_never_served(
    recapture: RateCardV2,
) -> None:
    # luna has not been routed to us; it is pinned because the pool is a lower
    # bound on the billable model set, not its definition. The rates are the
    # published LongCo GlobalStandard meter values, not an extrapolation from
    # sol or terra.
    assert recapture.resolve_pricing_key("gpt-5.6-luna-2026-07-09") == "gpt-5.6-luna"
    rates = recapture.rates_for("gpt-5.6-luna")
    assert rates is not None
    assert (rates.input, rates.output, rates.cached) == (
        Decimal("2.0"),
        Decimal("9.0"),
        Decimal("0.2"),
    )
    assert rates.reasoning == rates.output


def test_whole_5_6_family_is_present_and_distinctly_priced(recapture: RateCardV2) -> None:
    family = {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
    assert family <= set(recapture.rates)
    # Three tiers, three prices — a copy-paste that collapsed two of them into
    # one rate would silently mis-bill the arm this change exists to fix.
    inputs = {recapture.rates[k].input for k in family}
    assert len(inputs) == 3


# --------------------------------------------------------------------------- #
# Provenance: no rate without a meter behind it
# --------------------------------------------------------------------------- #


_ROW = re.compile(r"^ {2}(?P<key>[A-Za-z0-9][\w.\-]*):\s*\{")


def _rows_with_preceding_comments(text: str) -> dict[str, str]:
    """Map each ``rates:`` row key to the contiguous comment block above it."""

    lines = text.splitlines()
    found: dict[str, str] = {}
    for i, line in enumerate(lines):
        match = _ROW.match(line)
        if not match:
            continue
        block: list[str] = []
        j = i - 1
        while j >= 0 and lines[j].lstrip().startswith("#"):
            block.append(lines[j])
            j -= 1
        found[match.group("key")] = "\n".join(reversed(block))
    return found


@pytest.mark.parametrize("card_path", [FROZEN, RECAPTURE], ids=["frozen", "recapture"])
def test_every_rate_row_cites_the_retail_meter_it_came_from(card_path: Path) -> None:
    # The card's standing claim is that no rate is guessed. That is only
    # auditable if each row carries the meterId it was read from, so this is
    # enforced structurally rather than trusted — including for rows added
    # later, which is exactly how the 5.6 gap arose in the first place.
    card = RateCardV2.from_yaml(card_path)
    blocks = _rows_with_preceding_comments(card_path.read_text(encoding="utf-8"))
    for key in card.rates:
        assert key in blocks, f"{card_path.name}: rate row {key} has no comment block"
        assert "id=" in blocks[key], f"{card_path.name}: rate row {key} cites no meterId"
