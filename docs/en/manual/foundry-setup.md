# Foundry hands-on setup manual · per-experiment setup A–Z

This page lays out, start to finish, how to run each experiment as a **real Azure AI
Foundry run rather than a mock simulation**. It gathers resource provisioning (`az`),
model selection, KB (grounding) setup, system prompts, the fan-out/ensemble
mechanism, and the per-experiment settings in one place.

!!! note "What you need first — three prerequisites"
    On the Azure side, these three are all you need to begin:

    1. **One Azure AI Foundry resource** (a Cognitive Services / Azure OpenAI account) — e.g. `aoai-foundry-iq-demo-ext`.
    2. **One `model-router` deployment** — this one gives you cross-provider routing (the downstream OpenAI · xAI · DeepSeek · Meta models need no separate deployment; only Anthropic Claude is the exception).
    3. **The `Cognitive Services OpenAI User` role** — grant it to the calling principal (user/service principal) and calls go out with keyless **Entra** auth. No API key is used.

    This repository **does not create infrastructure** — it attaches to an
    already-deployed resource and measures. To point an ensemble arm directly at a
    specific partner model, just add that deployment name to the fleet YAML (BYO). IaC
    provisioning is a follow-up companion asset. For the full procedure see §1.

!!! success "This is all measured (`measured = true`)"
    The numbers below come from calling real deployments with keyless **Microsoft
    Entra ID**. Foundry's single `model-router` deployment actually branched one
    problem set (5 curated tasks) like this:

    | The real model the router chose | Vendor | Count |
    | --- | --- | --- |
    | `gpt-5.4` | OpenAI | 3 |
    | `grok-4-1-fast-reasoning` | xAI | 2 |

    Capture snapshot: [`samples/responses/foundry-arena-measured.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/foundry-arena-measured.json).
    Reproduce: `cost-router foundry arena --live --max-output-tokens 3000`.

    This snapshot is honest history captured from the initial **5-series routing
    resource** (`aoai-router5-ext-faf57f`) — provenance is preserved as-is. The current
    **go-forward resource is `aoai-foundry-iq-demo-ext`** (eastus) below, and it works
    with the same keyless method: the frontier is `gpt-5.6-sol`, GPT-5.4 keeps only
    `mini`/`nano`, and seven multi-provider partners are added on top.

---

## 0. Two planes — routing vs grounding

This demo's Azure resources split into **two planes** with distinct roles — both now
consolidated on **one Foundry resource** (`aoai-foundry-iq-demo-ext`, eastus). Not
mixing them is the key to understanding it. (Initially there was a separate 5-series
resource for routing, and [the measured snapshots in §4·§5](#4-fanout) were captured
there — that history is left as-is, and the setup from here on uses the single
demo-ext resource.)

| Plane | Resource | Deployments/resources | What it does |
| --- | --- | --- | --- |
| **Routing plane** | `aoai-foundry-iq-demo-ext` (`rg-foundry-iq-demo-ext`, eastus) | `model-router` + multi-provider fleet (`gpt-5.6-sol` · `gpt-4o` · `gpt-5.4-mini` · `gpt-5.4-nano` + 7 partners) | Per-prompt model selection · inference (arena · live experiments) |
| **Grounding plane** | the **same** `aoai-foundry-iq-demo-ext` + `srch-foundry-iq-demo-ext` (Azure AI Search) | `text-embedding-3-large` + a vector index | KB embedding · search (RAG grounding) |

- **The arena/head-to-head experiments use the routing plane only** (inference only,
  no KB).
- **KB grounding is optional.** You use the grounding plane only when you want to
  attach source documents to an experiment ([§2](#2-kb)).

---

## 1. Provision the routing plane (`az`)

The commands that actually built this demo, to be run once. The values are pulled out
into shell variables so they paste cleanly.

```bash
# 0) context — pin the tenant/subscription
az login --tenant <TENANT_ID> --use-device-code   # headless/sandbox uses device-code
az account set --subscription <SUBSCRIPTION_ID>

RG=rg-foundry-iq-demo-ext
LOC=eastus
ACCT=aoai-foundry-iq-demo-ext     # must be globally unique (the demo-ext resource)

# 1) resource group
az group create -n "$RG" -l "$LOC"

# 2) AI Services (=Foundry) account — disable local auth so only keyless is used
az cognitiveservices account create \
  -n "$ACCT" -g "$RG" -l "$LOC" \
  --kind AIServices --sku S0 \
  --custom-domain "$ACCT" \
  --assign-identity \
  --api-properties disableLocalAuth=true       # key auth OFF → Entra ID only
```

### 1-1. Create the deployments — Model Router + multi-provider fleet

Model Router is a selection layer that **works on its own with a single deployment** —
deploy just that one and it branches per prompt across not only the OpenAI GPT-5
family but xAI Grok · DeepSeek · Meta Llama · gpt-oss too, **with no separate
deployment** (only Anthropic Claude is the exception, needing a direct deployment).
The fleet deployments below are not the router but what the arena's **direct-call /
fan-out arms** (cheapest · premium · ensemble) use, reproducing exactly the
deployments actually stood up on this demo's `aoai-foundry-iq-demo-ext`
([`samples/fleet/foundry-ext-full.fleet.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/fleet/foundry-ext-full.fleet.yaml) is canonical).

```bash
# the router (the one-does-it-all selection layer)
az cognitiveservices account deployment create \
  -g "$RG" -n "$ACCT" \
  --deployment-name model-router \
  --model-name model-router --model-version 2025-11-18 \
  --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10

# Azure OpenAI surface (provider=openai) — frontier/mid/cheap tiers
# (frontier=gpt-5.6-sol·gpt-4o, mid=gpt-5.4-mini, floor=gpt-5.4-nano)
for M in "gpt-5.6-sol:2026-07-09" "gpt-4o:2024-11-20" "gpt-5.4-mini:2026-03-17" "gpt-5.4-nano:2026-03-17"; do
  NAME="${M%%:*}"; VER="${M##*:}"
  az cognitiveservices account deployment create \
    -g "$RG" -n "$ACCT" \
    --deployment-name "$NAME" \
    --model-name "$NAME" --model-version "$VER" \
    --model-format OpenAI \
    --sku-name GlobalStandard --sku-capacity 10
done
```

The 7 partner/OSS models go on the **same resource · same Entra identity**, but their
wire path is Azure AI Model Inference (`*.services.ai.azure.com/models`) and their
`--model-format` differs per publisher (not OpenAI). Create the deployment names,
models, and versions below exactly, filling in `--model-format` after checking it with
`az cognitiveservices account list-models`:

| Deployment (`deployment`) | Model (`--model-name`) | Version |
| --- | --- | --- |
| `deepseek-v4-pro` | `DeepSeek-V4-Pro` | `2026-04-23` |
| `mistral-large-3` | `Mistral-Large-3` | `1` |
| `grok-4-1-fast-reasoning` | `grok-4-1-fast-reasoning` | `1` |
| `kimi-k2-6` | `Kimi-K2.6` | `2026-04-20` |
| `llama-4-maverick` | `Llama-4-Maverick-17B-128E-Instruct-FP8` | `1` |
| `cohere-command-a-plus` | `Cohere-command-a-plus-05-2026` | `1` |
| `phi-4-reasoning` | `Phi-4-reasoning` | `1` |

```bash
# check the model-format/version per publisher → deploy per the table above
az cognitiveservices account list-models -g "$RG" -n "$ACCT" \
  --query "[?!starts_with(name,'gpt') && name!='model-router'].{name:name, version:version, format:format}" -o table

# verify — the final deployment list
az cognitiveservices account deployment list -g "$RG" -n "$ACCT" \
  --query "sort_by([].{name:name, model:properties.model.name, version:properties.model.version}, &name)" -o table
```

### 1-2. Grant the keyless role (Entra ID)

A data-plane inference call needs the **`Cognitive Services OpenAI User`** role (the
management role *Contributor* cannot do inference).

```bash
SCOPE=$(az cognitiveservices account show -g "$RG" -n "$ACCT" --query id -o tsv)
az role assignment create \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --role "Cognitive Services OpenAI User" \
  --scope "$SCOPE"
```

### 1-3. Wire `.env` (no secrets)

Copy `.env.sample` to `.env` and fill in **endpoint + deployment only**. Leave the key
box empty — when it is empty the bridge switches to Entra ID automatically.

```bash
AZURE_AI_FOUNDRY_ENDPOINT=https://aoai-foundry-iq-demo-ext.cognitiveservices.azure.com/
AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router
AZURE_AI_FOUNDRY_AUTH=entra        # optional — auto entra when there is no key
# AZURE_AI_FOUNDRY_API_KEY=        # leave empty (keyless)

# multi-provider fleet + rates (which deployment backs each arm / measured billing rates)
FOUNDRY_FLEET_PATH=samples/fleet/foundry-ext-full.fleet.yaml
FOUNDRY_PRICING_PATH=samples/pricing/foundry-ext-full.yaml
# leave the partner/OSS surface endpoint empty to derive it from the resource name
# (https://aoai-foundry-iq-demo-ext.services.ai.azure.com/models)
# AZURE_AI_FOUNDRY_INFERENCE_ENDPOINT=
```

```bash
cost-router foundry status          # credentialed: yes / auth method: Microsoft Entra ID (keyless)
```

!!! tip "Not a single value is committed"
    `.env` is gitignored, and `status` shows the endpoint down to the host only and
    masks the key. The keyless path has no key to store in the first place.

---

## 2. KB (grounding) setup — optional {#2-kb}

To attach **source documents** (an internal wiki, repo docs, and so on) to an
experiment, build a vector index and ground on it. Since routing and grounding are now
on the **same resource** (`aoai-foundry-iq-demo-ext`), you use the embedding
(`text-embedding-3-large`) right here and only attach Azure AI Search for the search.

```bash
GRG=rg-foundry-iq-demo-ext
GACCT=aoai-foundry-iq-demo-ext          # holds text-embedding-3-large (same resource as routing)
SEARCH=srch-foundry-iq-demo-ext         # Azure AI Search

# 1) confirm the embedding deployment (create it if absent)
az cognitiveservices account deployment create \
  -g "$GRG" -n "$GACCT" \
  --deployment-name text-embedding-3-large \
  --model-name text-embedding-3-large --model-version 1 \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 150

# 2) Search service (skip if it already exists)
az search service create -g "$GRG" -n "$SEARCH" -l centralus --sku Standard

# 3) grant the role so Search reads the embedding account keyless
SID=$(az search service show -g "$GRG" -n "$SEARCH" --query id -o tsv)
az role assignment create \
  --assignee "$(az search service show -g "$GRG" -n "$SEARCH" --query identity.principalId -o tsv)" \
  --role "Cognitive Services OpenAI User" \
  --scope "$(az cognitiveservices account show -g "$GRG" -n "$GACCT" --query id -o tsv)"
```

Then build the **vector index** (fields: `id`, `content`, `contentVector` (dim 3072,
`text-embedding-3-large`)), and chunk → embed → upsert your documents. At query time
you embed the question, pull the top-k chunks with a kNN search, and inject them as the
**context block of the system prompt** ([§3](#3-system-prompt)).

!!! note "KB is honestly 'optional'"
    The current bundled experiments (arena · curated) are **inference-only** and use no
    KB. The procedure above is the standard recipe for attaching an experiment that
    needs grounding (e.g. a repo-grounded review). Even with a KB attached, cost is
    measured as embedding + search + inference usage.

---

## 3. Generate the system prompt {#3-system-prompt}

The system prompt pins the experiment's **role · output contract**. In code it is
injected per task via `ArenaTask.system` (optional); with none, only the raw user
prompt is sent. Recommended system prompt per experiment:

| Experiment | system prompt (gist) |
| --- | --- |
| hero | "You are a senior engineer. Give an accurate, minimal answer/code; if unsure, state your assumptions." |
| curated | "Read each problem's acceptance criteria first, and give only answers that meet them." |
| ensemble | (the same prompt per arm for a fair comparison — the same system to every member of the fan-out slate) |
| adaptive | "For a high-value task, present the reasoning step by step; for a low-value one, be terse." |
| limits | "Be terse. Assume retry/rate-limit conditions and answer idempotently." |
| model-router | (no system — only the raw prompt, so the router picks the model by difficulty) |

When using a KB, append a context block at the end of the system prompt:

```text
<context>
{{top-k chunks — with source attribution}}
</context>
Answer based only on the context above; if it is not there, say "I don't know".
```

Inject it in code:

```python
from router.foundry_arena import ArenaTask
task = ArenaTask(
    task_id="t-0006",
    title="Unit tests for merge_intervals",
    prompt="Write unit tests for merge_intervals …",
    system="You are a meticulous test engineer. Always include boundary/empty-input/unsorted cases.",
)
```

---

## 4. Fan-out & ensemble mechanism {#4-fanout}

The four strategies (arms) ride **one problem** at once so cost and latency are
measured. Each arm is a real deployment call.

| arm | Deployment | Billing | What it shows |
| --- | --- | --- | --- |
| `cheapest` | `gpt-5.4-nano` | single-call | The cheapest floor |
| `premium` | `gpt-5.4` | single-call | The naive frontier ceiling |
| `ensemble` | `gpt-5.4-nano + gpt-5.4-mini + gpt-5.4` (parallel fan-out) | **sum-all-fanout** | Call all → accept only the best = the **fan-out tax** |
| `router` | `model-router` | winner-only | Foundry selects one model per prompt |

- **Fan-out** calls the whole slate in **parallel** (`ThreadPoolExecutor`), so latency
  is the *slowest* call (a max, not a sum). Cost is the **sum of all** (the tax).
- **The router** calls once and bills only the winning model's cost.

### Measured results (5 curated tasks, `max_completion_tokens=3000`)

!!! note "This table is honest measured history from the initial 5-series routing resource"
    The numbers/models below (`gpt-5.4`, `grok`) and the `premium=gpt-5.4` in the arm
    table above are as captured on `aoai-router5-ext-faf57f` — not rewritten, to
    preserve provenance. On **go-forward** (`aoai-foundry-iq-demo-ext`) the
    `premium`/frontier arm becomes `gpt-5.6-sol` and `ensemble` expands to the whole
    multi-provider bench (the `roles` in
    [`samples/fleet/foundry-ext-full.fleet.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/fleet/foundry-ext-full.fleet.yaml) are canonical). New measurements on demo-ext are re-captured on approval.

| arm | 5-task total | Avg latency | Note |
| --- | --- | --- | --- |
| `cheapest` | **$0.001191** | 9,079 ms | ~13× cheaper than frontier |
| `premium` | $0.015368 | 4,112 ms | reasoning-OFF default deployment |
| `ensemble` | $0.022046 | 8,325 ms | most expensive = the fan-out tax |
| `router` | $0.020806§ | 12,182 ms | grok×2 + gpt-5.4×3, reasoning ON |

!!! danger "§ the `router` row's amount is **incomplete** — do not compare its amount with the other arms"
    Model Router billing is synthetic: the **router input-token markup** + the input
    and output of the chosen sub-model. The capture above applied only the sub-model
    rates, so the `router` amount is **missing one billed component** — not an
    approximation, but incomplete. We left the original artifact and hashes untouched
    and marked it with the versioned annotation
    [`samples/annotations/legacy-router-pricing.annotation.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/annotations/legacy-router-pricing.annotation.json),
    which the CLI · reports · dashboard · replay enforce (fail-closed without it).
    Because the markup rate of the time is not pinned in the repository, we **did not
    re-price it** — the original amount is kept as history instead of an estimate and
    excluded from cost/savings claims. `cheapest` · `premium` · `ensemble`, which call
    a single deployment directly, are not subject to the markup and are **unaffected**.

!!! quote "An honest observation — projection and measurement differ"
    In the offline experiments (synthetic signals) the router is **cost-optimizing**,
    so it comes out as 'the cheapest'. But the **real Foundry model-router is
    quality-optimizing** — it sends most any coding problem to a reasoning model
    (grok · gpt-5.4). This is an observation about **model selection**, confirmed by
    the response's `model` field:

    - `t-0006` (unit tests): the router chose `grok-4-1-fast-reasoning` while the
      premium arm called `gpt-5.4` directly — different backends
    - `t-0004` (design plan): the router chose `gpt-5.4` **with reasoning on**,
      spending 158 reasoning tokens — the premium arm (reasoning off) spent 0

    **We claim no amount-based winner here** — per the § warning above, the
    router-derived amount is incomplete, so a "the router is cheaper/more expensive"
    comparison does not hold. Structurally, the **call-count** difference remains: the
    router is 1 call / 1 bill per prompt, fan-out is N calls / N bills.

    Usage and latency are **measured**; correctness (accuracy) is **ungraded** (inject
    a grader to measure it).

---

## 5. How the router selects — how does it pick? {#5-selection}

When you send a prompt to the `model-router` deployment, Foundry looks at
**difficulty · required capability** and picks a sub-model. The response's `model`
field carries **the model it actually chose**. Branches observed by actually sending
prompts of differing difficulty (measured):

| Prompt character | The real model the router chose | Vendor |
| --- | --- | --- |
| Trivial question (2+2, translation) | `gpt-oss-120b` | Open-source GPT |
| Short transform / easy code | `gpt-5.4-mini` | OpenAI |
| Code · reasoning (refactor, review, proof) | `grok-4-1-fast-reasoning` | xAI |
| Heavy design/architecture | `gpt-5.4` | OpenAI |

- **Nothing to configure** — the router selects automatically. You call once with
  `model=model-router`.
- **Read the selection in code**: `RouterOutcome.model` (after normalization,
  `gpt-5.4-2026-03-05` → `gpt-5.4`). The arena rates by this value and tallies it into
  `router_model_mix`.

```bash
# observe directly what the router picks per prompt (measured)
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl --synth --json \
  | jq '.model_counts'          # e.g. {"gpt-5.4-2026-03-05": 3, "grok-4-1-fast-reasoning": 2}
```

---

## 6. Per-experiment setup {#6-per-experiment}

How each of the six experiments runs — **with which model, which prompt, and how**.
`Measured status` means whether it is actually measurable in this repository right now.

### 6-1. hero — the hero (before/after)
- **Model**: after routing (`model-router`) vs the naive ceiling (`gpt-5.4`).
- **KB**: none. **system**: senior-engineer role (§3).
- **Run (measured)**: the `router` vs `premium` arms of
  `cost-router foundry arena --live` are the before/after as-is.
- **Measured status**: ✅ cost·latency measured / accuracy ungraded.
- Related: [experiment 01 · the hero](../lab-notebook/01-hero.md)

### 6-2. curated — the curated head-to-head
- **Model**: all four arms (`gpt-5.4-nano`/`gpt-5.4`/fan-out/`model-router`).
- **Input**: `samples/telemetry/curated-arena-live.sample.jsonl` (includes
  prompts+acceptance).
- **KB**: none. **system**: acceptance-first compliance (§3).
- **Run (measured)**: `cost-router foundry arena --live --max-output-tokens 3000`.
- **Measured status**: ✅ cost·latency measured / accuracy ungraded.
- Related: [experiment 02 · the curated sample](../lab-notebook/02-curated.md)

### 6-3. ensemble — the ensemble fan-out tax
- **Model**: the fan-out slate `gpt-5.4-nano + gpt-5.4-mini + gpt-5.4` (parallel).
- **KB**: none. **system**: identical for the whole slate (fair comparison).
- **Mechanism**: [§4](#4-fanout) — calling all and summing the bill is the tax; latency
  is the max.
- **Measured status**: ✅ tax (summed cost) · latency measured. The measured
  $0.022046 (the most expensive) makes the tax actually visible.
- Related: [experiment 05 · the ensemble fan-out tax](../lab-notebook/05-ensemble-fanout.md)

### 6-4. adaptive — the adaptive fan-out dial
- **Model**: a low-value task is a router single call; only a high-value task is
  promoted to fan-out.
- **Dial**: `compare_min_value` (offline `budget.py`). Live, you branch the slate
  conditionally so it calls the `ensemble_arm` only when the task value is at or above
  the threshold, else the `router_arm`.
- **KB**: none. **system**: value-based verbosity (§3).
- **Measured status**: ⚙️ the router/fan-out arms are measurable. The dial-threshold
  policy is exposed as an input variable (the `FleetSlate`/value threshold in
  [§7](#7-code) below).
- Related: [experiment 06 · the adaptive fan-out dial](../lab-notebook/06-fanout-dial.md)

### 6-5. limits — the rate-limit/failure wall
- **Model**: apply concurrent load to a single tier to observe 429/throttling.
- **KB**: none. **system**: terse · idempotent (§3).
- **Caution**: forcing real 429s affects cost/quota. In the demo we recommend
  demonstrating **concurrency · retry backoff** in code and observing the wall
  (fail-wall) on a low-`--sku-capacity` deployment.
- **Measured status**: ⚙️ latency/success-rate are measurable (load-injected). By
  default it safely stays a projection.
- Related: [experiment 07 · the routing layer](../lab-notebook/07-model-router.md)

### 6-6. model-router — the routing layer (single call)
- **Model**: a single `model-router` deployment. Auto-selects grok/gpt-5.4/gpt-oss and
  so on per prompt ([§5](#5-selection)).
- **KB**: none. **system**: none (so the router picks by difficulty).
- **Run (measured)**: `cost-router foundry live --live …` → the real branches in
  `model_counts`.
- **Measured status**: ✅ **the repository's first `measured = true`** — grok×2 +
  gpt-5.4×3. Note, though, that **the amount is incomplete** (missing the router input
  markup → see § above). We claim only model selection · usage · latency · auth.
- Related: [experiment 09 · live routing](../lab-notebook/09-live-routing-proof.md)

---

## 7. A clean run-code tour {#7-code}

The experiment runner is designed with **readability** as the top priority
(`src/router/foundry_arena.py`).

### 7-1. Environment — one transport, deployments by name

```python
from router.foundry_arena import FoundryFleet, FleetSlate, ArenaTask

fleet = FoundryFleet.from_env()          # one keyless client (Entra ID)
slate = FleetSlate()                     # cheapest/premium/ensemble/router deployment names
call  = fleet.call("gpt-5.4-nano", ArenaTask("t-1", "…"))   # any deployment by name
# call.model / call.usage / call.latency_ms / call.provenance == "live"
```

- **One transport** (`FoundryFleet`) builds the keyless SDK client once, calls any
  deployment by name, and measures usage · latency alongside.
- **The strategies are pure functions**:
  `cheapest_arm/premium_arm/ensemble_arm/router_arm(fleet, task, slate, pricing) ->
  ArmResult`. With no global state or hidden side effects, they test with no network by
  injecting a fake client.

### 7-2. Input variables — clear via types

```python
@dataclass(frozen=True)
class ArenaTask:      # one experiment input
    task_id: str; prompt: str; title: str = ""; system: str | None = None

@dataclass(frozen=True)
class FleetSlate:     # which deployment backs which arm
    router:   str = "model-router"
    cheapest: str = "gpt-5.4-nano"
    premium:  str = "gpt-5.4"
    ensemble: tuple[str, ...] = ("gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.4")
```

Change only `--workload` (the prompt JSONL) · `--pricing` (the rate YAML) ·
`--max-output-tokens` (reasoning headroom) and the experiment input is fully
controlled.

### 7-3. Ledger management — verify via hash chain + cost replay

```python
from router.foundry_arena import MeasuredArenaLedger
ledger = MeasuredArenaLedger(path=Path("runs/arena.jsonl"), pricing=pricing)
for outcome in outcomes:
    ledger.record(outcome)       # one task = one ledger line (sealed by a hash chain)
ledger.flush()                   # append-only JSONL
```

- **The offline audit ledger** (`src/router/ledger/record.py`,
  [the audit ledger](ledger.md)) is by contract always `measured = false`.
- **The measured ledger** (`MeasuredArenaLedger`) is **for real live calls only**, the
  one place `measured = true` provenance lives. Splitting the two enforces the honesty
  boundary in code.
- The measured ledger now has the **same two integrity guarantees** as the offline
  ledger (`src/router/ledger/measured.py`):
    - **Tamper detection** — each line is sealed with a `record_hash` over the
      canonical payload and chained to the prior line with `previous_hash`. A single
      changed byte breaks the chain.
    - **Deterministic cost replay** — each line carries the `pricing_snapshot` (rate
      table) used to score it, so verification re-derives every call cost from **the
      recorded token usage × that rate table** and confirms the match. The measured
      usage is fixed evidence, and the cost is a pure function of it.

```bash
# verify the measured ledger: hash chain + cost replay
cost-router ledger measured-replay --ledger runs/arena.jsonl
```

```text
records: 5
replayed: 5
  → each recorded call cost re-derived from its usage × the pinned rate card
  → router arm cost is pricing incomplete — missing Router input markup
     Model Router-derived cost omits the router input-token markup component. Retained as historical output; not publishable and not usable for a savings claim.
status: PASS
```

The last two lines appear only when the ledger has a `model-router` row — because the
router-derived amount is **incomplete**, missing the router input markup. If such a row
exists but the pricing annotation cannot be read, verification
**closes with `status: FAIL`**.

`foundry arena --ledger` runs this verification automatically right after the flush,
printing `ledger: +N measured row(s) → … (hash-chain + cost-replay: OK)`.

### 7-4. Reproduce in one go

```bash
# live 4-way arena (cost·latency measured) + save the report/ledger
cost-router foundry arena --live --max-output-tokens 3000 \
  --out runs/arena-measured.json --ledger runs/arena.jsonl

# router single-call measurement (confirm the per-prompt model branch)
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl --synth --json
```

!!! danger "Honesty-boundary summary"
    - **Cost·latency = measured** (real usage × rates, real wall-clock). Rates default
      to the public list; for exact tenant spend, inject your tenant rates with
      `--pricing`.
    - **Accuracy = ungraded** (`accuracy: ungraded`). Whether an answer is right is
      measured only when you inject a grader.
