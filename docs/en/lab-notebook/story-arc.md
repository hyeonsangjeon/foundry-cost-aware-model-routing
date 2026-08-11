# Story arc — one thesis

!!! abstract "One-sentence thesis"
    **Observe, escalate only when you must — and stay honest about coverage.**
    Cost-aware routing tries the cheapest model first and escalates *only the tasks
    that fail*, saving money without losing coverage. And every shortcut — deleting
    the expensive model, ensembling everything, picking once up front — carries a
    **measurable price**. This repository meters that price offline and
    deterministically, and **never inflates it** (`labels.measured = false`).

This page is a **map for reading the core arc (01–07)** of the repository's
[experiments 01–12](index.md) as **one story**. Each experiment answers the question
the previous one left open, and together they defend the single sentence above.
[Experiment 08 (arena)](08-arena.md) is the **epilogue that narrows that story to a
single task**. The derivation and reproduction steps for individual numbers live on
each experiment page; "when, and what was done" lives in the [dev log](/foundry-cost-aware-model-routing/ko/lab-notebook/devlog/).

!!! info "What are these experiments evidence of — four axes on top of 'selection'"
    Azure AI Foundry's **built-in Model Router** already solves the *selection*
    problem — picking one model per prompt — well (one deployment, cross-provider —
    [experiment 07](07-model-router.md)). This repository does not replace it; it is
    the **layer on top**. The experiments below meter that layer's four axes offline
    and deterministically — *multi-provider routing is the built-in table-stakes; the
    differentiators are these four*:

    - **① Verify-then-adopt** — accept only when execution signals are clean, escalate the failures (gains in 01·02, guardrails in 03·04)
    - **② Ensemble axis** — expose and meter the fan-out tax (winner-only vs summing all = 3.74×) ([05](05-ensemble-fanout.md))
    - **③ Cost governor** — dial that tax down with a budget gate (3.74× → $0) ([06](06-fanout-dial.md))
    - **④ Audit trace** — seal measured runs into a tamper-evident, cost-replayable ledger ([09](09-live-routing-proof.md)·[10](10-measured-ledger.md))

    And **[experiment 07](07-model-router.md)** *is* that contrast — the generic
    **`single-call`** arm that picks once and stops vs the observe-then-escalate
    **mix**. *Selection is the built-in router's job; verification, governance, and
    audit are this repo's.*

## The story at a glance — the journey (01–08)

| # | Question | Result | What it proves |
| --- | --- | --- | --- |
| [01 · Flagship](01-hero.md) | Routing on a realistic 100-task workload? | 100% coverage, **−25.5%** ($2.23 → $1.66) | the gain is real |
| [02 · Curated](02-curated.md) | Five tasks you can follow by eye? | 100% coverage, **−56.7%** ($0.13 → $0.06) | verify the gain task by task |
| [03 · Coverage cliff](03-coverage-cliff.md) | Delete the expensive fallback to save more? | looks cheaper, but coverage **100% → 67%** (−33%p) | cost without pinned coverage is meaningless |
| [04 · No free lunch](04-no-free-lunch.md) | A workload where only the top model passes? | 100% coverage, **0%** saved | routing doesn't invent savings that aren't there |
| [05 · Ensemble tax](05-ensemble-fanout.md) | What does "just ensemble everything" cost? | 100% coverage, −47% + fan-out **3.74×** | ensembling isn't free (a hidden tax) |
| [06 · Fan-out dial](06-fanout-dial.md) | Get rid of that tax? | coverage/savings flat, tax **3.74× → $0** | the tax is a dial |
| [07 · Routing layer](07-model-router.md) | Pick once (`single-call`)? | single-call **52%** vs mix **100%** (+48%p gain) | the value of observing = coverage regained |
| [08 · Arena](08-arena.md) *(epilogue)* | This one problem, four ways? | router = cheapest correct but **slowest** (sequential) | even the winner pays a **latency** price |

All numbers are deterministic offline projections over synthetic data
(`measured = false`). The canonical source for these figures is
[offline experiment results](../manual/projection-results.md). Experiment 08's
**latency is a newly introduced illustrative projection**, with a different origin
than cost and accuracy (offline projections).

## Read it in three acts

### Act 1 · The gain — "routing really does save" (01–02)

The story opens with a **claim**: instead of the naive approach of billing the
premium model on every task, try the cheapest candidate first and escalate only when
its own checks fail — and you save money without losing coverage.

- **Experiment 01** shows this at realistic scale (100 synthetic tasks): **100%**
  coverage, **−25.5%** cost.
- **Experiment 02** narrows the same story to **five eyeball-checkable tasks**,
  verifying task by task why routing wins (−56.7%).

So far this is a "routing is good" demo. An honest question follows immediately —
*can you **fake** this gain?*

### Act 2 · The honest limits — "but you can't fake the gain" (03–04)

Act 2 **attacks** routing. It refutes two easy tricks that lower the cost number
alone.

- **Experiment 03 (coverage cliff):** **delete** the expensive fallback model from
  the policy and the bill *looks* cheaper at −38.9%. But grade with the same signals
  and coverage collapses **100% → 67%** — a third of the tasks lose a model that
  would pass. → *a cost comparison that doesn't pin coverage is meaningless.*
- **Experiment 04 (no free lunch):** on a workload where every task is genuinely hard
  and **only the top model passes**, routing = naive, **0%** saved. → *routing
  doesn't invent savings that aren't there; it spends honestly on hard work.*

The lesson of Act 2: the gain is real, but it is **neither infinite nor free to
inflate**. So the natural next move — *push harder?*

### Act 3 · Expensive shortcuts and their price — "push harder? each shortcut has a tax" (05–07)

Act 3 meters the two directions of "harder" and the price of each.

- **Experiment 05 (ensemble tax):** direction ①, **run everything**. Ensemble
  (compare) all candidates and take only the winner: coverage fills up, but the
  fan-out spends **3.74× the winner** (the cost of running the losing candidates too
  = a hidden tax). Metrics in the Azure Foundry shape record that tax.
- **Experiment 06 (fan-out dial):** the honest fix for 05. That tax isn't a fixed
  cost but a **dial** — a single budget-gate threshold turns the tax off
  (**3.74× → $0**) while coverage (100%) and savings (47%) stay flat.
- **Experiment 07 (routing layer):** direction ②, **pick once**. The generic
  **`single-call`** arm that picks one model per prompt up front is cheap and simple,
  but with no escalation its coverage collapses to **52%** on synthetic data. The
  observe-then-escalate mix fills **100%** at **comparable cost** (**+48%p** gain). →
  *the value of observing = coverage regained.*

Act 3 comes full circle: not ensemble (all) nor single-call (one) but
**observe-then-escalate** is the sweet spot — 05 and 07 meter the price of the two
extremes, and 06 connects them with a dial.

## Epilogue · Arena — narrowing to one problem (08)

Acts 1–3 compared the **whole** workload in aggregate. [Experiment 08
(arena)](08-arena.md) narrows the same frontier to **a single task**, answering the
first question a new user asks — *"on this one problem, how much does each approach
spend, how slow is it, and does it get the answer right?"* — and it adds one axis the
previous seven experiments didn't cover: **latency**.

On the default task `t-0003` the router wins on cost and accuracy (a correct answer
2.5× cheaper than premium) but is the **slowest** on latency — because escalation is
sequential, so the latency of the failed attempts adds up. In other words, the lesson
of Act 3 ("every approach has a price") applies to **the router itself**: the price
for the cost and coverage the router regains is, here, **latency**. This latency,
though, is an **illustrative projection** (`measured = false`, not wall-clock), so it
is marked as a different origin than cost and accuracy (offline projections).

What the epilogue confirms: you can hold the whole story **in one hand** — the cost,
(illustrative) latency, and correctness of four approaches on a single task, on one
screen. And the thesis that no axis is free holds up even at the resolution of an
individual task.

## Measured coda · from projection to measurement, and to audit (09 · 10)

Acts 1–3 and the epilogue (08) are all offline projections (`measured = false`,
placeholder models). [Experiment 09 · Live routing](09-live-routing-proof.md) crosses
that boundary: it wires the same routing idea into a **real Azure AI Foundry Model
Router**, the repository's first **`measured = true`** measurement — a single
`model-router` deployment really forked, task by task, to **`gpt-5.4` and
`grok-4-1-fast-reasoning`** (keyless Entra). This coda does *not* replace the story
above: the honesty of 01–08 is still an offline projection, and 09 is **separate live
evidence** that the idea is observed on the real frontier too (accuracy ungraded, cost
rates illustrative — the honesty boundary is spelled out in experiment 09).

[Experiment 10 · Measured ledger](10-measured-ledger.md) hardens that measured record
one step further — it seals the live run into a canonical audit ledger with **tamper
detection (hash chain) + cost replay (a sealed rate card)**, so anyone can reproduce
`PASS` in one line without credentials or a network, and **a single edited byte
fails**. Just as the offline track (01–08) is protected by the [reproducibility
contract](index.md#shared-methodology), the measured track (09) is now protected by an
**independently re-verifiable ledger** — the two audits kept separate so neither blurs
the other's honesty label.

## The axis of honesty — every experiment is one of two kinds

This is why the repository is not a demo but a collection of **honest experiments**.
Without exception, the seven experiments are one of two kinds:

- **show a gain** — 01, 02
- **refute a way to fake or misread the gain (03 · 04 · 05 · 07), or control its price (06)**

Repositories with nothing but victory slides are common. Here, **five experiments
(03–07) are guardrails** — they rebut "this looks cheaper, but actually…" themselves.
[Experiment 08](08-arena.md) is a third kind — a **lens**: it adds no new claim and
instead **shows** the same honest machine at single-task resolution (noting, though,
that the latency axis is a new illustrative projection).

## The reproducibility contract keeps the story honest

Each experiment's `expect` contract **fails CI** if the story drifts. The contract
grows in three directions:

| Contract | What it stops | Introduced |
| --- | --- | --- |
| `min_coverage` · `min_delta_pct` · `min_tasks` | the gain quietly disappearing | 01 |
| `max_delta_pct` (ceiling) | an inflated **phantom saving** | [04](04-no-free-lunch.md) |
| `max_tax_ratio` (ceiling) | a quietly leaking **fan-out tax** | [06](06-fanout-dial.md) |
| `min_escalation_gain` (floor) | observe-then-escalate slipping out unnoticed | [07](07-model-router.md) |

So each turn of the storyline is pinned by an **executable contract**: if anyone
changes the code and distorts the numbers, the pipeline blocks it. For field details,
see [experiment configuration (YAML)](../manual/experiments.md).

## One frontier in a single picture — the whole story in one image

The [dashboard](../manual/dashboard.md)'s **cost × coverage frontier** overlays five
strategies on one scatter:

- `all-mini` (lower-left) — cheap but coverage collapses,
- `all-premium` (upper-right) — 100% coverage but maximum cost,
- `all-ensemble` (far right) — 100% coverage but the **most expensive** through fan-out ([05](05-ensemble-fanout.md)),
- `single_call` (blue dot, below the corner) — pick once, **low coverage** ([07](07-model-router.md)),
- `cost-aware mix` (**upper-left win-win corner**) — the only one with full coverage + low cost.

All of Act 3 is in this one picture: only mix sits in the corner, and every other
strategy loses on one axis or another —
[live demo](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1).

## Reading paths

- **5 minutes (executive):** this page's thesis + the journey table → [experiment 01](01-hero.md).
- **15 minutes (practitioner):** the three acts above → check the five strategies on the [dashboard frontier](../manual/dashboard.md) → one guardrail of interest ([03](03-coverage-cliff.md) / [05](05-ensemble-fanout.md) / [07](07-model-router.md)).
- **Everything:** [introduction and methodology](index.md) → 01–07 in order → narrow to one task in [experiment 08 · arena](08-arena.md) → [dev log](/foundry-cost-aware-model-routing/ko/lab-notebook/devlog/).

## Reproduce everything

```bash
pip install -e .
cost-router experiment list                       # list registered experiments
for e in hero curated limits ensemble adaptive model-router; do
  cost-router experiment run "$e"                  # each experiment's before/after + contract
done
cost-router policy regression \
  --candidate experiments/policies/cost-cut.yaml --synth   # experiment 03 coverage cliff
cost-router compare                                # experiment 08 arena — one problem, four ways
```

Every command runs offline and deterministically, without a network or credentials,
and produces the same numbers every time — numbers that are always
`labels.measured = false`.
