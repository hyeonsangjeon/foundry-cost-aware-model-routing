# Story arc (EN summary) — ten experiments, one thesis

!!! abstract "One-sentence thesis"
    **Observe, escalate only when you must — and stay honest about coverage.**
    Cost-aware routing tries the cheapest model first and escalates *only the
    tasks that fail*, saving money without losing coverage. Every shortcut —
    deleting the expensive model, ensembling everything, picking once up front —
    carries a **measurable price**. This repo meters that price offline and
    deterministically, and **never inflates it** (`labels.measured = false`).

This is the one-page English companion to the Korean
[story arc](story-arc.md); each experiment page has the full derivation and a
reproducibility contract.

## Complementary to the built-in Model Router — a layer on top of "selection"

Azure AI Foundry's **built-in Model Router** already solves *selection* well —
one deployment, cross-provider, picks a model per prompt
([experiment 07](07-model-router.md)). This repo does not replace it; it's the
layer **on top**. Multi-provider routing is table-stakes; the differentiators are
four axes this notebook meters offline:

- **① Verify-then-adopt** — accept only when execution signals are clean, escalate the failures (gains in 01–02, guardrails in 03–04).
- **② Ensemble axis** — expose and meter the fan-out tax (winner-only vs summing all = 3.74×) ([05](05-ensemble-fanout.md)).
- **③ Cost governor** — dial that tax down with a budget gate (3.74× → $0) ([06](06-fanout-dial.md)).
- **④ Audit trace** — seal measured spend into a tamper-evident, cost-replayable ledger ([09](09-live-routing-proof.md) · [10](10-measured-ledger.md)).

**[Experiment 07](07-model-router.md)** *is* that contrast: single-call selection
(**52%**) vs observe-then-escalate mix (**100%**) at ~the same cost. *Selection is
the built-in router's job; verify / escalate / govern / audit is this repo's.*

## The ten experiments at a glance

| # | Question | Result | What it proves |
| --- | --- | --- | --- |
| [01 · Hero](01-hero.md) | Routing on a realistic 100-task workload? | 100% coverage, **−25.5%** ($2.23 → $1.66) | the gain is real |
| [02 · Curated](02-curated.md) | Five tasks you can follow by eye? | 100% coverage, **−56.7%** | verify the gain task by task |
| [03 · Coverage cliff](03-coverage-cliff.md) | Delete the expensive fallback to save more? | looks cheaper, but coverage **100% → 67%** | cost without pinned coverage is meaningless |
| [04 · No free lunch](04-no-free-lunch.md) | A workload where only the top model passes? | 100% coverage, **0%** saved | routing never invents savings that aren't there |
| [05 · Ensemble tax](05-ensemble-fanout.md) | What does "just ensemble everything" cost? | 100% coverage, −47% + fan-out **3.74×** | ensembling isn't free (a hidden tax) |
| [06 · Fan-out dial](06-fanout-dial.md) | Keep the savings but drop the tax? | coverage/savings flat, tax **3.74× → $0** | the tax is a dial |
| [07 · Routing layer](07-model-router.md) ⭐ | Pick once, no escalation (any single-call router)? | single-call **52%** vs mix **100%** (+48%p) | the value of observing = coverage regained |
| [08 · Arena](08-arena.md) *(epilogue)* | One problem, four ways? | router = cheapest correct but **slowest** (sequential) | even the hero pays a **latency** price |
| [09 · Live routing proof](09-live-routing-proof.md) *(measured)* | Wired to a real Model Router, what does it pick? | one call split `gpt-5.4`×3 + `grok-4-1-fast-reasoning`×2 — first **`measured=true`**, keyless Entra | selection is real and cross-provider |
| [10 · Measured ledger](10-measured-ledger.md) *(measured)* | Can anyone re-verify the spend wasn't tampered with? | sealed **hash-chained, cost-replayable** ledger — one edited byte fails replay | the audit trail is tamper-evident |

All offline numbers are deterministic projections over synthetic data
(`measured = false`); rounded to cents here — the ledger and `--json` keep full
precision for re-verification. Only experiments 09–10 carry `measured = true`
(a live call sealed into the ledger).

## Read it in three acts

**Act 1 · The gain (01–02).** The story opens with a claim: instead of billing the
premium model on every task, try the cheapest candidate first and escalate only
when its own checks fail — you save money without losing coverage. Experiment 01
shows it at realistic scale (100% coverage, −25.5%); experiment 02 narrows it to
five eyeball-checkable tasks (−56.7%). Then the honest question follows: *can you
fake this gain?*

**Act 2 · The honest limits (03–06).** The middle attacks the claim. Deleting the
expensive fallback makes the bill *look* cheaper but collapses coverage 100% → 67%
(03); a workload where only the top model passes yields 0% savings — routing
doesn't invent savings that aren't there (04); "just ensemble everything" reaches
full coverage but spends 3.74× the winner, a hidden fan-out tax (05); and that tax
turns out to be a single budget dial you can turn down to $0 while savings stay flat
(06). The gain is real, but it is neither infinite nor free to inflate.

**Act 3 · Selection vs verification, then proof (07–10).** Experiment 07 is the
centerpiece: single-call selection — the shape of any per-prompt router, including
the built-in Model Router — holds only 52% coverage, while layering
observe-then-escalate on top reaches 100% at comparable cost (+48%p). Experiment 08
adds the latency axis (the cheapest correct answer is also the slowest). Finally
09–10 wire a **real** Model Router deployment in as that arm over keyless Entra,
capture the first `measured=true` run, and seal it into a hash-chained ledger that
anyone can replay — one edited byte fails verification. *Selection is solved by the
product; this repo is the verify / escalate / govern / audit layer on top.*
