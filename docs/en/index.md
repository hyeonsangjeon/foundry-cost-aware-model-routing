# Foundry cost-aware model routing

> The decision this repo encodes: **for each task, send it to the cheapest model that still passes, escalate to a higher model only when the pass-rate gain outweighs the cost, and prove the result.**

Welcome to the manual and lab notebook. The experiments here are offline and
deterministic — no network, no external calls, the same result every time you run
them. This site lays out how to **install, run, see for yourself, and reproduce**
those experiments.

!!! success "Measured result (measured=true · directional)"
    In a real Azure Foundry measurement, the `router-cost` arm was
    **95.2% cheaper** than `direct-premium`, with the pass-rate gap within
    **4.17%p** — a directional (publishable) result from 24 tasks · a single tenant ·
    one measurement.
    → [Routing-mode measured results dashboard](manual/03d-results.md)

Before the numbers, here is where they come from — starting with the layer this
repo occupies.

!!! abstract "A layer on top of the built-in Model Router — four differentiators"
    **Model selection** is already handled well by Azure AI Foundry's **built-in
    Model Router** (one deployment, cross-provider). This repo does not **replace**
    it; it **sits on top** — ① **verify** with execution signals and escalate only
    the failures · ② meter the **ensemble tax** · ③ gate spend with a **cost
    governor** · ④ seal every decision into an **audit ledger**. *Selection is the
    built-in's job; verification, governance, and audit are this repo's.*

The centerpiece that puts this contrast on one screen is
[experiment 07 · Routing layer](lab-notebook/07-model-router.md). There the
**pass rate** is the **share of tasks that passed (were solved) all the way
through** — the offline CLI and experiment contract emit this value as `coverage`,
which is a different metric from the **grading coverage** (share of cells graded)
reported separately in measured results ([Glossary](manual/glossary.md)). Over
synthetic data, the generic **`single-call`** arm holds only a **52%** pass rate,
while observe-then-escalate fills **100%** (`measured = false` projection).

To read those numbers correctly, though, you have to tell two tracks apart and know
their limits.

!!! warning "Honesty first — two tracks"
    This repo **separates two kinds of numbers by label**. Here `measured` is the
    label for whether a number was measured from a real model call or only computed
    offline. The **projection track (experiments 01–08)** is an offline projection
    over synthetic data (`labels.measured = false`), so the model names are all
    generic placeholders too. The **measured track (experiments 09 · 10 · 11 · 12)**
    is measured from real Azure Foundry calls (`measured = true`) and uses real
    deployment names. But `evidence_tier = directional` — 24 tasks · a single tenant ·
    one measurement, so it is a **directional signal**, not statistical confidence
    (experiment 11 is **VOID**, below its pre-registration bar — void or not, a
    measurement is still a measurement). Check the label on each page — your actual
    savings depend on your workload mix and rates.

## Check it in 30 seconds

```bash
git clone https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing
cd foundry-cost-aware-model-routing
pip install -e .          # install the cost-router console script
cost-router hero          # run the flagship experiment in one shot
```

The before/after block that `cost-router hero` prints (100 synthetic-workload tasks):

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $2.23
  AFTER   cost-aware routing                   $1.66
  SAVED   $0.57  (25.5% lower)  at 100.0% coverage

spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.0003
  naive   deep-reasoner  $0.0071   (24.1x more)

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 25.5% ≥ 20.0%
  PASS  tasks: 100 ≥ 100
```

Watch it live in the dashboard, in one step:

```bash
cost-router hero --serve   # runs, then opens the offline dashboard
# open http://127.0.0.1:8000/?run=1 in your browser → auto-plays on load
```

!!! success "Try it with no install · interactive offline demo"
    If you want to see the results before you clone, an **interactive offline demo**
    is ready to open right in your browser. The moment it opens, the before/after and
    spotlight for 100 synthetic-workload tasks auto-play.

    [:material-rocket-launch: Open the interactive offline demo (auto-play)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1){ .md-button .md-button--primary target=_blank }

    This demo is a static file pre-rendered on GitHub Pages — no server, no network
    calls, no secrets, and **it is not a billed live dashboard**. The numbers are
    generated the same way as `cost-router hero`.

## Not a mockup but your own Azure — the browser cockpit

The offline demo above is a **read-only mockup of results already measured and
committed**. To run the same screen **live against your own Foundry deployment**, use
the local cockpit — no credentials ever go into the browser (`127.0.0.1` only + a
session token; Entra is read from `az login`).

!!! note "The cockpit is mid-update to the latest measurement wiring (issue #55)"
    The cockpit's run path has not yet received the latest measurement wiring (03B-2
    v2 rates · 03D-1 grading bridge) — for example, the live client does not inject
    `max_output_tokens`, so it uses the default of 512. For **accurate measurement
    right now, use the CLI path**. For the wiring details see
    [issue #55](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/issues/55),
    and for the method see the [measurement protocol](manual/measurement-protocol.md).

```bash
az login                      # keyless Entra — no input field in the browser
cost-router dashboard --live  # prints a 127.0.0.1 + random-port + session-token URL
```

From connection check → outgoing prompts and dry-run cost → **approve and run** (the
human gate) → live progress → replay of the `results/measured/<exp>/<run-id>`
snapshot, all in the **same UI** as the mockup. For the setup end to end, just follow
[Foundry setup](manual/foundry-setup.md) → [Customize · cockpit](manual/customize.md)
→ [audit ledger](manual/ledger.md) in order.

## What you'll see

<div class="grid cards" markdown>

-   :material-check-decagram: **Measured result · router-cost 95.2% savings**

    ---

    A real Azure Foundry measurement (`measured=true` · directional): `router-cost`
    is **95.2% cheaper** than `direct-premium`, with a pass-rate gap within 4.17%p.
    → [Routing-mode measured results](manual/03d-results.md)

-   :material-rocket-launch: **Flagship run mode**

    ---

    With the experiment set up, one command gives you before/after, the spotlight,
    and a reproducibility self-check in one shot.
    → [Experiment 01 · Flagship run](lab-notebook/01-hero.md)

-   :material-scale-balance: **Same pass rate, lower cost**

    ---

    The cheapest arm collapses to a 22% pass rate; the premium arm hits 100% but
    costs the most. Routing **holds the pass rate at 100%** while lowering cost.
    → [Core concepts](manual/concept.md)

-   :material-file-document-check: **A reproducible audit ledger**

    ---

    Every routing decision is recorded in a hash-chained JSONL, and replaying the
    stored inputs verifies it byte for byte. → [audit ledger](manual/ledger.md)

-   :material-flask: **Lab notebook**

    ---

    A lab notebook recording the methodology, honesty labels, and actual figures.
    → [Lab notebook intro](lab-notebook/index.md)

</div>

## Next steps

- First time → [30-second install](manual/install.md)
- Why route this way → [Core concepts](manual/concept.md)
- Want to build your own experiment → [Experiment config (YAML)](manual/experiments.md)
- This project's claim boundaries → [Honesty Charter](honesty.md)
