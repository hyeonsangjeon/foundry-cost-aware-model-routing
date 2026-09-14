# Foundry cost-aware model routing

> **Start with the cheapest model that can pass the task. Check its result; if it
> fails, try the next model. Use a more expensive model only when the higher pass
> rate is worth the extra cost, and record the evidence needed to verify the result.**

These pages show how to install the project, run its experiments, inspect the
results, and reproduce them. The experiments come in two kinds. The **measured track**
(experiments 09, 10, 11, 12 and 13) calls Azure Foundry for real. The **projection
track** (experiments 01–08) validates the routing logic offline on synthetic data; it
makes no network or external calls, so the same inputs produce the same results.

!!! success "Measured result (measured=true · directional)"
    In experiment 12, one real Azure Foundry measurement found that the `router-cost` arm
    (Model Router in Cost mode) cost **95.2% less** than `direct-premium` (calling the
    premium model directly · `gpt-5.6-sol`). The pass-rate gap was within **4.17 percentage points (pp)**.
    That run measured 24 tasks × 4 arms × 3 repeats in a single tenant on a single
    occasion, so it is a directional signal, not statistical confidence. The run passed
    its pre-registered reporting criteria.

    Two conditions travel with this number. The pass-rate gap came from transport
    timeouts rather than from code quality, and
    [experiment 13](lab-notebook/13-router-modes-rate-card-gap.md) later found that an
    arm's cost is a property of the backends the router happened to serve that day, not
    a stable property of its mode.
    → [Routing-mode measured results dashboard](manual/routing-measured-results.md)

Before comparing results, separate what Foundry already does from what this repository adds.

!!! abstract "What this repo adds after the built-in Model Router chooses a model"
    Azure AI Foundry's **built-in Model Router** already handles **model selection**
    from one deployment, including across providers. This repo does not **replace**
    it. It adds four controls to the run: ① check the answer with execution signals
    and try a higher model only after a failure (**verify**) · ② total the extra
    candidate-call cost · ③ stop at the approved spending limit · ④ write every
    decision to a replayable record (**audit ledger**). *The built-in selects the
    model. This repo checks the result, controls spending, and records what
    happened.*

An **arm** is one comparison strategy evaluated against the same workload under the same
measurement plan; every page here uses the word that way
([Glossary](manual/glossary.md)).
[Experiment 07 · Single-call routing vs observe-then-escalate](lab-notebook/07-model-router.md)
compares one model choice with a process that can try again after a failure. On synthetic data, the
generic **`single-call`** arm chooses once and stops, and its **pass rate** is **52%**.
Observe-then-escalate checks the first result and moves up only after a failure,
reaching **100%**. Both numbers are a `measured = false` projection.

Here **pass rate** means the **share of tasks that passed (were solved) all the way
through**. The offline CLI and experiment contract call this field `coverage`.
Measured results also report **grading coverage**, the share of planned cells that
produced an answer that could be graded; it is a different metric with a different
denominator ([Glossary](manual/glossary.md)).

The two tracks below tell you whether a number was computed offline or measured from
real calls.

!!! warning "Honesty first — two tracks"
    Every result belongs to one of two tracks. The `measured` label says whether a
    number came from a real model call or an offline calculation.

    The **projection track (experiments 01–08)** runs on synthetic data
    (`labels.measured = false`). It makes no real model calls, and its model names are
    generic placeholders. These numbers are not measured savings.

    The **measured track (experiments 09 · 10 · 11 · 12 · 13)** uses real Azure Foundry
    calls (`measured = true`) and real deployment names. Its evidence is still
    `evidence_tier = directional`. Experiments 09 and 10 measured 5 curated tasks;
    experiments 11, 12 and 13 measured 24 tasks × 4 arms × 3 repeats = 288 planned
    cells. All of them are a single tenant and a single measurement, so they are a
    **directional signal**, not statistical confidence. Experiment 11 is **VOID** on two
    independently sufficient grounds: its quality arm fell below the pre-registered
    grading-coverage floor, and 43.4% of its cells were unpriced. It remains a
    measurement, but it cannot support the comparison that was planned. Check the label
    on each page. Your actual savings depend on your workload mix and rates.

## Check it in 30 seconds

```bash
git clone https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing
cd foundry-cost-aware-model-routing
pip install -e .          # install the cost-router console script
cost-router hero          # run the default cost-and-coverage experiment in one shot
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
    To see the results before cloning, open the **interactive offline demo** in your
    browser. It automatically plays the before/after and the representative task for 100
    synthetic-workload tasks.

    [:material-rocket-launch: Open the interactive offline demo (auto-play)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1){ .md-button .md-button--primary target=_blank }

    This demo is a static file pre-rendered on GitHub Pages — no server, no network
    calls, no secrets, and **it is not a billed live dashboard**. The numbers are
    generated the same way as `cost-router hero`.

## Not a mockup but your own Azure — the local browser run screen

The offline demo above is read-only: it shows results that were already measured and
committed. The local version runs the same screen live against your own Foundry
deployment. Credentials never enter the browser; it connects only to `127.0.0.1`
with a session token, while Entra reads the sign-in from `az login`.

```bash
az login                      # keyless Entra — no input field in the browser
cost-router dashboard --live  # prints a 127.0.0.1 + random-port + session-token URL
```

The same UI first checks the connection, then shows the outgoing prompts and dry-run
cost. Nothing runs until a person chooses **approve and run**. It
then shows live progress and replays the `results/cockpit/<run-id>` snapshot.
For the full setup, follow [Foundry setup](manual/foundry-setup.md) →
[Customize · the browser run screen](manual/customize.md) → [audit ledger](manual/ledger.md) in order.

## What you'll see

<div class="grid cards" markdown>

-   :material-check-decagram: **Measured result · router-cost 95.2% savings**

    ---

    In experiment 12, a real Azure Foundry measurement (`measured=true` · directional),
    `router-cost` cost **95.2% less** than `direct-premium`. The pass-rate gap was
    within 4.17 pp, and it came from timeouts rather than code quality.
    → [Routing-mode measured results](manual/routing-measured-results.md)

-   :material-rocket-launch: **Default run mode**

    ---

    One command prints the before/after result, the representative task, and the
    reproducibility self-check.
    → [Experiment 01 · Try-cheap-first routing](lab-notebook/01-hero.md)

-   :material-scale-balance: **Same pass rate, lower cost**

    ---

    Always choosing the cheapest model solves only 22% of the tasks. Always choosing
    the premium model reaches 100% but costs the most. Routing starts cheaper and
    moves up after a failure, so it **holds the pass rate at 100%** while lowering cost.
    → [Core concepts](manual/concept.md)

-   :material-file-document-check: **A reproducible audit ledger**

    ---

    Every routing decision goes into a hash-chained JSONL. Replaying the stored
    inputs must reproduce it byte for byte. → [audit ledger](manual/ledger.md)
-   :material-flask: **Lab notebook**

    ---

    The lab notebook records how each experiment ran, which honesty labels apply,
    and what numbers came out.
    → [Lab notebook intro](lab-notebook/index.md)

</div>

## Next steps

- First time → [30-second install](manual/install.md)
- Why route this way → [Core concepts](manual/concept.md)
- Want to build your own experiment → [Experiment config (YAML)](manual/experiments.md)
- This project's claim boundaries → [Honesty Charter](honesty.md)
