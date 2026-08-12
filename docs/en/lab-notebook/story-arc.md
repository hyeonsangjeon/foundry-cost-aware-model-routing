# Story arc — one thesis

!!! abstract "One-sentence thesis"
    **Observe, escalate only when you must — and stay honest about coverage.**
    Cost-aware routing tries the cheapest model first and escalates *only the tasks
    that fail*, saving money without losing coverage. And every shortcut — deleting
    the expensive model, ensembling everything, picking once up front — carries a
    **measurable price**. This repository meters that price offline and
    deterministically, and **never inflates it** (`labels.measured = false`).

This page puts the repository's [experiments 01–12](index.md) in order. For the core
experiments 01–07, it states what changed, what result came out, and what question
the next experiment answers. [Experiment 08 (arena)](08-arena.md) applies the same
comparison to one task. Each experiment page contains the calculation and
reproduction steps; "when, and what was done" lives in the
[dev log](/foundry-cost-aware-model-routing/ko/lab-notebook/devlog/).

!!! info "What are these experiments evidence of — four axes on top of 'selection'"
    Azure AI Foundry's **built-in Model Router** already picks one model per prompt
    from one cross-provider deployment ([experiment 07](07-model-router.md)). This
    repository does not replace that selection. The experiments below test four
    additional actions offline and deterministically:

    - **① Verify-then-adopt** — accept only when execution signals are clean, escalate the failures (gains in 01·02, guardrails in 03·04)
    - **② All-candidate call accounting** — count every candidate instead of the winner alone (3.74×) ([05](05-ensemble-fanout.md))
    - **③ Cost governor** — use a budget gate to reduce those extra calls (3.74× → $0) ([06](06-fanout-dial.md))
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
| [05 · Ensemble tax](05-ensemble-fanout.md) | What does "just ensemble everything" cost? | 100% coverage, −47% + fan-out **3.74×** | every candidate call is billed |
| [06 · Fan-out dial](06-fanout-dial.md) | Remove unnecessary fan-out? | coverage/savings unchanged, extra-call ratio **3.74× → $0** | fewer calls, same result |
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

Act 3 tests two ways to do more work and records what each one costs.

- **Experiment 05 (ensemble tax):** **run everything.** Ensemble (compare) calls all
  candidates and keeps one winner. Coverage fills, but the run costs
  **3.74× the winner** because the losing candidates are billed too. Azure
  Foundry-shaped metrics record those calls.
- **Experiment 06 (fan-out dial):** compared with experiment 05, raise one
  budget-gate threshold so fewer tasks
  call every candidate. The extra-call ratio falls **3.74× → $0** while coverage
  (100%) and savings (47%) stay unchanged.
- **Experiment 07 (routing layer):** direction ②, **pick once**. The generic
  **`single-call`** arm that picks one model per prompt up front is cheap and simple,
  but with no escalation it reaches only **52%** coverage on synthetic data. The
  observe-then-escalate mix checks the result and moves up after a failure, reaching
  **100%** at **comparable cost** (**+48%p** gain).

Act 3 brings together experiments 05 and 07; experiment 06 controls the extra calls.
Together, the results favor **observe-then-escalate**: calling every candidate adds
cost, while choosing once leaves failed tasks unresolved. The middle process checks
the result and calls another model only after failure.

## Epilogue · Arena — narrowing to one problem (08)

Acts 1–3 compared the **whole** workload in aggregate. [Experiment 08
(arena)](08-arena.md) applies the same comparison to **a single task**, answering the
first question a new user asks — *"on this one problem, how much does each approach
spend, how slow is it, and does it get the answer right?"* — and adds **latency**,
which the previous seven experiments did not cover.

On the default task `t-0003`, the router returns a correct answer 2.5× cheaper than
premium but has the **highest latency**. Escalation is sequential, so time spent on
failed attempts is added to the final attempt. This latency is an **illustrative
projection** (`measured = false`, not wall-clock), not a measured timing. Its source
therefore differs from the cost and accuracy projections.

The earlier phrase "every approach has a price" refers here to the added latency.
This is the Act 3 latency result for the router itself.

The one-task table puts cost, illustrative latency, and correctness for four
approaches on one screen. No approach is best on every measure.

## Measured record · from projection to measurement and audit (09 · 10)

Acts 1–3 and the epilogue (08) are all offline projections (`measured = false`,
placeholder models). [Experiment 09 · Live routing](09-live-routing-proof.md) crosses
that boundary: it wires the same routing idea into a **real Azure AI Foundry Model
Router**, the repository's first **`measured = true`** measurement — a single
`model-router` deployment really forked, task by task, to **`gpt-5.4` and
`grok-4-1-fast-reasoning`** (keyless Entra). This result does *not* turn experiments 01–08 into measurements. They remain offline
projections. Experiment 09 is **separate live evidence** that one real deployment
made those routing choices (accuracy ungraded, cost rates illustrative — the honesty
boundary is spelled out in experiment 09).

[Experiment 10 · Measured ledger](10-measured-ledger.md) hardens that measured record
one step further — it seals the live run into a canonical audit ledger with **tamper
detection (hash chain) + cost replay (a sealed rate card)**, so anyone can reproduce
`PASS` in one line without credentials or a network, and **a single edited byte
fails**. Just as the offline track (01–08) is protected by the [reproducibility
contract](index.md#shared-methodology), the measured track (09) is now protected by an
**independently re-verifiable ledger** — the two audits kept separate so neither blurs
the other's honesty label.

## Every experiment is one of two kinds

The repository keeps positive and negative results together. The seven experiments
are one of two kinds:

- **show a gain** — 01, 02
- **refute a way to fake or misread the gain (03 · 04 · 05 · 07), or control its price (06)**

**Five experiments (03–07) are guardrails**: they test ways a cost result can be
misread or made to look better. [Experiment 08](08-arena.md) adds no new aggregate
claim. It shows the same comparison for one task and labels latency as a new
illustrative projection.

They test the claim "this looks cheaper, but actually…" with the recorded values.

## The reproducibility contract keeps the story honest

Each experiment's `expect` contract **fails CI** if the story drifts. The contract
grows in three directions:

| Contract | What it stops | Introduced |
| --- | --- | --- |
| `min_coverage` · `min_delta_pct` · `min_tasks` | the gain quietly disappearing | 01 |
| `max_delta_pct` (ceiling) | an implausibly large saving | [04](04-no-free-lunch.md) |
| `max_tax_ratio` (ceiling) | too much cost from extra candidate calls | [06](06-fanout-dial.md) |
| `min_escalation_gain` (floor) | observe-then-escalate slipping out unnoticed | [07](07-model-router.md) |

So each turn of the storyline is pinned by an **executable contract**: if anyone
changes the code and distorts the numbers, the pipeline blocks it. For field details,
see [experiment configuration (YAML)](../manual/experiments.md).

## Five strategies in one cost-and-coverage chart

The [dashboard](../manual/dashboard.md) plots five strategies by cost and coverage:

- `all-mini` (lower-left) — cheap but low coverage,
- `all-premium` (upper-right) — 100% coverage but maximum cost,
- `all-ensemble` (far right) — 100% coverage but the **most expensive** through fan-out ([05](05-ensemble-fanout.md)),
- `single_call` (blue dot, below the corner) — pick once, **low coverage** ([07](07-model-router.md)),
- `cost-aware mix` (upper-left) — full coverage at low cost.

The chart summarizes Act 3. It shows the result directly: the mix has full coverage without the premium
or all-ensemble cost —
[live demo](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1).

## Reading paths

- **5 minutes (executive):** this page's thesis + the journey table → [experiment 01](01-hero.md).
- **15 minutes (practitioner):** the three acts above → compare the five strategies on the [dashboard chart](../manual/dashboard.md) → one guardrail of interest ([03](03-coverage-cliff.md) / [05](05-ensemble-fanout.md) / [07](07-model-router.md)).
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
