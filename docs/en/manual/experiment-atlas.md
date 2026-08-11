# Experiment Atlas — how each experiment is built

> **English visual manual.** The dashboard's **Experiments — click for the metrics** strip has six
> tabs — `adaptive`, `curated`, `ensemble`, `hero`, `limits`, `single-call`. Each one re-runs the
> *same* router over a workload and prints cost · coverage · fan-out tax under a reproducibility
> contract. This page opens the hood: **which models** each uses, **what it processes**, **which
> selection mechanism** (ordered escalation, fan-out, or single-call), and the **honest headline**.
> It ends with the **measured track** (the live Foundry bridge, experiments 09–12), linking out to the full Azure setup guide so you can stand the real thing up yourself.

!!! tip "The diagrams animate"
    The mechanism and architecture SVGs below are animated (they loop in your browser like a GIF) —
    watch the router walk the ladder, fan out, and pick a backend. Every number is an **offline
    deterministic projection** (`labels.measured=false`) *except* the live Foundry bridge in the
    final section, which is `measured=true`.

## At a glance

![Six experiments at a glance: hero and curated use ordered escalation, ensemble fans out, adaptive turns fan-out off, limits shows the honest floor, single-call compares one up-front pick to the mix](/foundry-cost-aware-model-routing/assets/experiments-overview.svg)

Same models, same pricing, same policy everywhere. Each experiment flips exactly **one dial** — the
workload, the fan-out gate, or the comparison arm — so you can read one idea at a time.

---

## The shared machinery

### 1 · The model ladder

Every experiment draws from one universe of candidate models. The routing **policy**
([`src/policy/seed_policy.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/policy/seed_policy.yaml))
maps each **task class** to an *ordered* list of candidates, cheapest first, each carrying two
priors: a **pass-rate** and a **`$/resolved`** (total dollars per resolved task).

![The model ladder: five candidate models ordered cheapest to priciest by dollars per resolved task](/foundry-cost-aware-model-routing/assets/models-ladder.svg)

| Task class | Ordered candidates (cheapest → priciest, `$/resolved`) |
| --- | --- |
| `plan` | swift-coder `0.40` · balanced-pro `1.10` · deep-reasoner `2.80` |
| `generate` | mini-fast `0.12` · swift-coder `0.35` · balanced-pro `1.05` |
| `test` | mini-fast `0.15` · swift-coder `0.38` · balanced-pro `1.00` |
| `validate` | mini-fast `0.14` · balanced-pro `0.95` · deep-reasoner `2.50` |
| `repo_patch` | swift-coder `0.55` · balanced-pro `1.40` · deep-reasoner `3.10` · premium-max `5.20` |

!!! note "The model names are generic stand-ins"
    `mini-fast … premium-max` are illustrative placeholders, not vendor products, and the priors are
    seeded (not measured). You replace them with values derived from your own routing telemetry. The
    **live** section at the bottom shows the real models the Azure Model Router actually selected
    (`gpt-5.4`, `grok-4-1-fast-reasoning`).

### 2 · Four decision layers

Under the hood, one task flows through four layers (detailed in [Core concepts](concept.md)):

```text
1. CLASSIFY  task → {plan, generate, test, validate, repo_patch}
2. POLICY    task class → ordered candidate models (pass-rate, $/resolved priors)
3. SELECT    cost-aware single route (cheapest-clean-first); escalate/fan-out on failure
4. GOVERN    a cost governor decides — before spending — whether a task is worth fanning out
```

Only **layer 3 (SELECT)** changes shape between experiments. There are exactly **three shapes**.

### 3 · The three selection mechanisms

=== "Ordered escalation"

    Walk candidates cheap → pricey. Accept the **first clean result** (self-verifiable signals:
    *applies · compiles · tests pass · lint/type pass*). Escalate **only** on a failed check. You are
    billed for the **accepted** model — the failed cheap attempts are observed, not charged as
    winners. This is where most of the savings come from.

    ![Cost-aware single route: try the cheapest candidate first, escalate only on a failed check, bill only the accepted model](/foundry-cost-aware-model-routing/assets/mechanism-ordered.svg)

    *Used by · `hero` · `curated` · `limits` · `adaptive`*  ·  code: `ordered_select()`

=== "Fan-out (ensemble)"

    Run **every** candidate in parallel (`compare` mode), score each by its execution signals, and
    keep the highest — ties break to the **cheapest passing** model. Every discarded candidate
    still incurs a call cost.

    ![Ensemble fan-out: run every candidate in parallel, keep the cheapest passing result, and pay for every discarded call](/foundry-cost-aware-model-routing/assets/mechanism-fanout.svg)

    *Used by · `ensemble`*  ·  code: `compare_select()`

=== "Single-call"

    Bucket each prompt by predicted difficulty and commit to **one** model up front — no fan-out, no
    escalation. It cannot correct a wrong up-front pick, so coverage drops. This is the *shape* of a
    productized router; the real one's pick-skill is proprietary and **measured** (see the last
    section).

    ![Single-call routing: pick one model per prompt up front by difficulty tier, with no escalation](/foundry-cost-aware-model-routing/assets/mechanism-single-call.svg)

    *Used by · `single-call`*  ·  code: `single_call_pick()`

---

## The six experiments

Every card lists **what it processes**, **which models**, **which mechanism**, the **dial** it turns,
the **headline** (re-derived live by the command shown), and a link to the full lab-notebook entry.

!!! info "How the six map to the four differentiators (atop the built-in router's selection)"
    Azure AI Foundry's **built-in Model Router** already handles *selection* — one deploy, cross-
    provider (Grok · DeepSeek · Llama · gpt-oss with no separate deploy; Claude the exception).
    The built-in already "routes many providers". These experiments test what happens after
    selection: **① verification-based adoption**
    (`hero`, `curated`, `limits`) · **② all-candidate call accounting** (`ensemble`) ·
    **③ the spending check before fan-out** (`adaptive`) · **④ the audit trace** (the measured bridge + ledger
    below). The **single-call** card compares one up-front pick with no escalation
    against observe-and-escalate. Its synthetic coverage numbers show the difference.

Each card **opens with a looping animation** that traces its real mechanism — flow dots, the
escalation ladder, or the fan-out — while the offline (`measured=false`) numbers count up live.
They are generated deterministically from the numbers above by
[`scripts/build_experiment_gifs.py`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/scripts/build_experiment_gifs.py)
(Pillow + ffmpeg).

### `hero` — same coverage, lower cost

![Animated hero loop: a naive lane sends every task to premium-max ($2.23) while the cost-aware lane tries mini-fast first, escalates once on a failed check, and keeps swift-coder — landing 25.5% cheaper at the same 100% coverage](/foundry-cost-aware-model-routing/assets/gif/hero.gif)

| | |
| --- | --- |
| **Processes** | 100 synthetic tasks (deterministic offline signals, `synth: true`) |
| **Models** | full ladder per class (mini-fast … premium-max) |
| **Mechanism** | **Ordered escalation** |
| **Dial** | none — the flagship default |
| **Headline** | **100% coverage · −25.5%** vs premium-on-every-task ($2.23 → $1.66) |
| **Contract** | `min_coverage 1.0`, `min_delta_pct 0.20`, `min_tasks 100` |

```bash
cost-router experiment run hero
```

The naive arm puts the *most expensive* candidate on every task (100% coverage, $2.23). Ordered
escalation keeps that 100% coverage but tries cheap-clean-first, landing 25.5% cheaper.
→ [Lab-notebook 01](../lab-notebook/01-hero.md) · canonical figures: [offline experiment results](projection-results.md)

### `curated` — five tasks you can read

![Animated curated loop: the same escalation ladder over five hand-labelled tasks, cheap-clean-first, landing 56.7% under premium-on-every-task](/foundry-cost-aware-model-routing/assets/gif/curated.gif)

| | |
| --- | --- |
| **Processes** | 5 hand-written offline signals (`samples/responses/routing-signals.sample.json`) |
| **Models** | full ladder per class |
| **Mechanism** | **Ordered escalation** |
| **Dial** | none — smallest "does it work?" check |
| **Headline** | **100% coverage · −56.7%** ($0.13 → $0.06) |
| **Contract** | `min_coverage 1.0`, `min_delta_pct 0.30`, `min_tasks 3` |

```bash
cost-router experiment run curated
```

Tiny enough to follow every routing decision by eye end-to-end.
→ [Lab-notebook 02](../lab-notebook/02-curated.md)

### `ensemble` — best-of-N, at a real cost

![Animated ensemble loop: the workload calls all five candidates in parallel, keeps the cheapest passing winner (swift-coder), and records ~3.7x total cost for all calls](/foundry-cost-aware-model-routing/assets/gif/ensemble.gif)

| | |
| --- | --- |
| **Processes** | 6 high-value tasks (`samples/responses/ensemble-fanout-signals.sample.json`) |
| **Models** | full ladder per class, **all** run per task |
| **Mechanism** | **Fan-out (compare)** |
| **Dial** | fan-out **on** for every task |
| **Headline** | **−47%** vs naive ($0.25 → $0.13) · all candidate calls cost **≈3.7×** the winners (winners ≈ $0.13, all calls ≈ $0.50) |
| **Contract** | `min_coverage 1.0`, `min_delta_pct 0.40`, `min_tasks 6` |

```bash
cost-router experiment run ensemble
```

Because several models pass each high-value task, best-of-N settles on the **cheapest passing**
model — still 47% under naive — but fanning out means paying for the losing calls too.
→ [Lab-notebook 05](../lab-notebook/05-ensemble-fanout.md)

### `adaptive` — the fan-out dial, turned off

![Animated adaptive loop: compare_min_value rises above every task value, reducing five parallel calls to one; extra-call ratio falls from 3.7x to 0.00x while 47% savings stay unchanged](/foundry-cost-aware-model-routing/assets/gif/adaptive.gif)

| | |
| --- | --- |
| **Processes** | the **same** 6 high-value tasks as `ensemble` |
| **Models** | full ladder per class |
| **Mechanism** | **Ordered escalation** (fan-out gated off) |
| **Dial** | `budget.compare_min_value: 1.1` — above every task's value (max 1.0) → **never fans out** |
| **Headline** | **identical −47% at 100% coverage**, with **extra-call ratio → 0.00×** |
| **Contract** | `min_coverage 1.0`, `min_delta_pct 0.40`, `max_tax_ratio 0.01`, `min_tasks 6` |

```bash
cost-router experiment run adaptive
```

Same workload, savings, and coverage as `ensemble`, but extra candidate-call cost falls to ~$0.
On this deterministic projection, single-route escalation already reaches the same cheapest-passing
winner as fan-out. A real best-of-N system can improve *quality*, so measure that improvement before
paying for the additional calls.
→ [Lab-notebook 06](../lab-notebook/06-fanout-dial.md)

### `limits` — there is no free lunch

![Animated limits loop: every cheap tier fails in turn (mini-fast, swift-coder, balanced-pro, deep-reasoner all red) so escalation climbs all the way to premium-max on every task — 0.0% savings, honest spend](/foundry-cost-aware-model-routing/assets/gif/limits.gif)

| | |
| --- | --- |
| **Processes** | 6 genuinely hard tasks where **only the priciest candidate passes** (`hard-tasks-signals.sample.json`) |
| **Models** | full ladder per class |
| **Mechanism** | **Ordered escalation** (climbs to the top every time) |
| **Dial** | none |
| **Headline** | **0.0% savings at 100% coverage** — routing == naive here |
| **Contract** | two-sided: `min_coverage 1.0`, `min_delta_pct 0.0`, **`max_delta_pct 0.0`** |

```bash
cost-router experiment run limits
```

The deliberate counter-weight to `hero`. Routing tries the cheap models, watches them fail, and
correctly escalates to the top model on every task. It does not invent savings — and the
**`max_delta_pct 0.0`** ceiling makes CI fail loudly if a future change ever fakes a "cheaper" number
on hard work.
→ [Lab-notebook 04](../lab-notebook/04-no-free-lunch.md)

### `single-call` — one pick vs observe-and-escalate { #model-router-one-pick-vs-observe-and-escalate }

![Animated single-call loop: a single-call lane picks one tier up front and stalls at 52% coverage, while the escalation lane observes cheap failures and raises only when needed to reach 100% coverage at the same cost band (+48 percentage points)](/foundry-cost-aware-model-routing/assets/gif/model-router.gif)

| | |
| --- | --- |
| **Role** | ⭐ **Centerpiece** — the direct contrast that justifies the layer atop the built-in router |
| **Processes** | 100 synthetic tasks |
| **Models** | full ladder per class |
| **Mechanism** | **Single-call** arm compared against the escalating **mix** |
| **Dial** | surfaces a `single_call` strategy arm alongside the mix |
| **Headline** | single-call **52%** coverage vs mix **100%** — an **escalation gain of +48%p** at comparable cost |
| **Contract** | `min_coverage 1.0`, `min_delta_pct 0.20`, `min_tasks 100`, **`min_escalation_gain 0.30`** |

```bash
cost-router experiment run single-call
```

A single-call router commits before it sees any check, so a wrong pick can't be corrected and
coverage of this synthetic arm drops to 52%. The observe-then-escalate mix reclaims full coverage
for nearly the same cost.

That figure is a projection of the generic *shape*, not a score for any shipped product. The real
Foundry Model Router's pick-skill is proprietary — that gap is exactly what the **measured** live
bridge captures next.
→ [Lab-notebook 07](../lab-notebook/07-model-router.md) · canonical figures: [offline experiment results](projection-results.md)

---

## Compare five strategies by cost and coverage

The dashboard places the single-call arms and routing strategies on one cost-and-coverage scatter:

![Cost versus coverage scatter of five strategies](/foundry-cost-aware-model-routing/assets/frontier.svg)

| Strategy | Selection | Cost | Coverage |
| --- | --- | ---: | ---: |
| `all-mini` | cheapest candidate on every task | **$0.19** | 22.0% |
| `single-call` | single difficulty-tiered pick | $1.59 | 52.0% |
| **`cost-aware mix`** | **cheapest-clean-first, escalate on fail** | **$1.66** | **100.0%** |
| `all-premium` (naive) | priciest candidate on every task | $2.23 | 100.0% |
| `ensemble-all` | fan out to every model, every task | $4.23 | 100.0% |

The **cost-aware mix** reaches 100% coverage at the lowest cost among the strategies
that reach full coverage. It costs less than `all-premium` and `ensemble-all`.

---

## From offline projection to measured routing

Everything above is an **offline projection**. To turn *model selection* into a real **measured**
result, deploy an Azure AI Foundry **Model Router** and let it route real prompts. You call **one**
deployment (`model="model-router"`); the router picks a backend **from its own managed roster** and
returns which one in `response.model`.

![Azure AI Foundry Model Router architecture with keyless Entra auth](/foundry-cost-aware-model-routing/assets/azure-architecture.svg)

!!! success "This is exactly how experiment 09 was proven"
    Through this one `model-router` deployment, curated prompts split live to **`gpt-5.4` (×3)** and
    **`grok-4-1-fast-reasoning` (×2)** — with distinct response-id fingerprints (`gpt-5.4` →
    `chatcmpl-…`, grok → a pure UUID) as backend provenance. Notably, **grok was never deployed by
    us** — the account holds only `model-router` + `gpt-5.4 / -mini / -nano`, proving the router
    routes to *its own* roster. Full evidence: [Lab-notebook 09 · live routing proof](../lab-notebook/09-live-routing-proof.md).

The complete keyless-Entra walkthrough — one `model-router` deployment, no API keys, wiring the repo,
and a single measured pass — is the copy-paste guide in [Foundry setup](foundry-setup.md). Once the
repo is wired, `cost-router foundry live --live` turns every curated task into a real `measured=true`
call. From there the **measured track** runs across four lab-notebook entries; the atlas lists them at
a glance and links out for the detail.

### `09` · live routing proof — `measured=true`

The architecture above *is* experiment 09: one `model-router` deployment, called keyless, that really
forks curated prompts to `gpt-5.4` (×3) and `grok-4-1-fast-reasoning` (×2). Because `grok` was never
deployed on the account, this is direct proof that the router selects from **its own** roster.
→ [Lab-notebook 09](../lab-notebook/09-live-routing-proof.md)

### `10` · the audit ledger

Seal that measured run so it cannot be quietly edited afterward: a canonical, hash-chained ledger that
is **tamper-evident** and **cost-replayable** against a sealed rate card, re-verified to `PASS` in one
line — flip a single byte and it fails. This is the **④ audit trace** the differentiators promised
above.
→ [Lab-notebook 10](../lab-notebook/10-measured-ledger.md)

### `11` · the paid router-mode run (VOID)

The first paid four-arm comparison (**$3.47 / $20**) is **VOID** under the preregistration committed
in advance — grading coverage came in at **79.2%**, below the **90%** per-arm floor. A negative result
kept as an asset by discipline: the predictions were overturned (Grok at 100%, not Claude; reasoning
tokens swallowing the output).

**Arm labels:** `router-cost` (Model Router in Cost mode) · `router-balanced` (Model Router
in Balanced mode) · `router-quality` (Model Router in Quality mode) · `direct-premium`
(calling the premium model directly · `gpt-5.6-sol`).

![Cost vs pass-rate scatter: direct-premium costs less and has a higher pass rate than router-quality; router-cost has the lowest cost at the same pass rate](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.en.svg)
*This scatter is experiment **12**'s publishable result — experiment 11's own paid run is VOID, so it has no chart of its own.*
→ [Lab-notebook 11](../lab-notebook/11-router-modes-void.md)

### `12` · the paid router-mode re-run (publishable)

Fix only the two causes experiment 11 identified, then re-run against the **same** preregistered gate:
grading coverage recovers **79.2% → 96.18%** and **all four arms PASS → publishable** (**$3.27 / $20**,
byte-identical replay). The three 03D charts below are this run's evidence.

![Horizontal bars of total cost per arm: router-cost $0.06, router-balanced $0.31, direct-premium $1.34, router-quality $1.56, each bar annotated with pass rate and cost-per-pass](/foundry-cost-aware-model-routing/assets/03d/arm-cost-comparison.en.svg)
![Stacked bars of the backends actually routed per arm: router-cost is 100% grok-4-1-fast-reasoning; router-quality splits across gpt-5 and gpt-5.5 with no grok; direct-premium is 100% gpt-5.6-sol](/foundry-cost-aware-model-routing/assets/03d/backend-distribution.en.svg)
→ [Lab-notebook 12](../lab-notebook/12-router-modes-measured.md) · full charts: [03D measured results](03d-results.md)

---

## What is measured, and what is not

| Claim | Live bridge | Offline experiments |
| --- | --- | --- |
| **Model selection** (which backend) | ✅ measured — real `response.model` | projected |
| **Token usage** (billed input/output/reasoning) | ✅ measured — provider usage | synthetic |
| **Wall-clock latency** | ✅ measured | not modeled |
| **Keyless auth** | ✅ real Entra bearer token | n/a |
| **Accuracy / coverage** | ⚠️ projected unless you inject a `grader` (`coverage_measured=false`) | projected |
| **Cost *rate*** (USD per token) | ⚠️ illustrative rate × real tokens — **not** your Azure bill | illustrative |

Every offline number on this page is `labels.measured=false`. Only the live bridge's *selection,
usage, latency, and auth* are `measured=true`. See the [Honesty compact](../honesty.md) for the full
boundary.
