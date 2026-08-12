# Foundry cost-aware model routing

> **Start with the cheapest model that can pass the task. Check its result; if it
> fails, try the next model. Use a more expensive model only when the higher pass
> rate is worth the extra cost, and record the evidence needed to verify the result.**

These pages show how to install the project, run its experiments, inspect the
results, and reproduce them. The experiments come in two kinds: one measures real
results by calling Azure Foundry (experiments 09 · 10 · 11 · 12), and the other
validates the routing logic offline on synthetic data (experiments 01–08). The
offline experiments make no network or external calls, so the same inputs produce
the same results.

!!! success "Measured result (measured=true · directional)"
    One real Azure Foundry measurement found that the `router-cost` arm (Model Router in
    Cost mode) cost **95.2% less** than `direct-premium` (calling the premium model
    directly · `gpt-5.6-sol`). The pass-rate gap was within **4.17%p**. This result
    comes from 24 tasks · a single tenant · one measurement, so it is directional
    (publishable), not statistical confidence.
    → [Routing-mode measured results dashboard](manual/03d-results.md)

Before comparing results, separate what Foundry already does from what this repository adds.

!!! abstract "What this repo adds after the built-in Model Router chooses a model"
    Azure AI Foundry's **built-in Model Router** already handles **model selection**
    from one deployment, including across providers. This repo does not **replace**
    it. It adds four controls to the run: ① check the answer with execution signals
    and try a higher model only after a failure (**verify**) · ② total the extra
    candidate-call cost (**ensemble tax**) · ③ stop at the approved spending limit
    (**cost governor**) · ④ write every decision to a replayable record (**audit
    ledger**). *The built-in selects the model. This repo checks the
    result, controls spending, and records what happened.*

[Experiment 07 · Routing layer](lab-notebook/07-model-router.md) compares one model
choice with a process that can try again after a failure. On synthetic data, the
generic **`single-call`** arm chooses once and stops, and its **pass rate** is **52%**.
Observe-then-escalate checks the first result and moves up only after a failure,
reaching **100%**. Both numbers are a `measured = false` projection.

Here **pass rate** means the **share of tasks that passed (were solved) all the way
through**. The offline CLI and experiment contract call this field `coverage`.
Measured results also report **grading coverage**, the share of cells that produced
an answer that could be graded; it is a different metric
([Glossary](manual/glossary.md)).

The two tracks below tell you whether a number was computed offline or measured from
real calls.

!!! warning "Honesty first — two tracks"
    Every result belongs to one of two tracks. The `measured` label says whether a
    number came from a real model call or an offline calculation.

    The **projection track (experiments 01–08)** runs on synthetic data
    (`labels.measured = false`). It makes no real model calls, and its model names are
    generic placeholders. These numbers are not measured savings.

    The **measured track (experiments 09 · 10 · 11 · 12)** uses real Azure Foundry
    calls (`measured = true`) and real deployment names. Its evidence is still
    `evidence_tier = directional`: 24 tasks · a single tenant · one measurement. That
    is a **directional signal**, not statistical confidence. Experiment 11 is
    **VOID** because it fell below its pre-registration bar; it remains a measurement,
    but it cannot support the comparison that was planned. Check the label on each
    page. Your actual savings depend on your workload mix and rates.

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
    To see the results before cloning, open the **interactive offline demo** in your
    browser. It automatically plays the before/after and spotlight for 100
    synthetic-workload tasks.

    [:material-rocket-launch: Open the interactive offline demo (auto-play)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1){ .md-button .md-button--primary target=_blank }

    This demo is a static file pre-rendered on GitHub Pages — no server, no network
    calls, no secrets, and **it is not a billed live dashboard**. The numbers are
    generated the same way as `cost-router hero`.

## Not a mockup but your own Azure — the browser cockpit

The offline demo above is read-only: it shows results that were already measured and
committed. The local cockpit runs the same screen **live against your own Foundry
deployment**. Credentials never enter the browser; it connects only to `127.0.0.1`
with a session token, while Entra reads the sign-in from `az login`.

!!! note "The cockpit is mid-update to the latest measurement wiring (issue #55)"
    The cockpit's run path does not yet include the latest measurement wiring (03B-2
    v2 rates · 03D-1 grading bridge). For example, the live client does not set
    `max_output_tokens`, so it uses the default of 512. For **accurate measurement
    right now, use the CLI path**. For wiring details, see
    [issue #55](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/issues/55),
    and for the method see the [measurement protocol](manual/measurement-protocol.md).

```bash
az login                      # keyless Entra — no input field in the browser
cost-router dashboard --live  # prints a 127.0.0.1 + random-port + session-token URL
```

The same UI first checks the connection, then shows the outgoing prompts and dry-run
cost. Nothing runs until a person chooses **approve and run** (the human gate). It
then shows live progress and replays the `results/measured/<exp>/<run-id>` snapshot.
For the full setup, follow [Foundry setup](manual/foundry-setup.md) →
[Customize · cockpit](manual/customize.md) → [audit ledger](manual/ledger.md) in order.

## What you'll see

<div class="grid cards" markdown>

-   :material-check-decagram: **Measured result · router-cost 95.2% savings**

    ---

    In a real Azure Foundry measurement (`measured=true` · directional), `router-cost`
    cost **95.2% less** than `direct-premium`. The pass-rate gap was within 4.17%p.
    → [Routing-mode measured results](manual/03d-results.md)

-   :material-rocket-launch: **Flagship run mode**

    ---

    One command prints the before/after result, the spotlight task, and the
    reproducibility self-check.
    → [Experiment 01 · Flagship run](lab-notebook/01-hero.md)

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
