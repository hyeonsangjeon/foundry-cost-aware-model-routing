# The live measured bridge · Azure Model Router

Everything else in the repository is an **offline projection over synthetic
telemetry** (`measured = false`). The `src/router/foundry_live.py` this page
describes is the **single isolated seam** that turns that projection into a
**measurement** — it sends real prompts to a real Azure AI Foundry **Model Router**
deployment, reads the actual model the router picked and the **token usage actually
billed**, and computes cost from that usage.

!!! danger "Honesty boundary — strict on purpose"
    - **You can measure spend, but (with this repository) not quality.** A live call
      returns real tokens, so `total_cost_usd` is genuinely measured spend. Whether
      each answer was *good* is measured only when you inject a **grader**; without
      one, coverage falls back to the offline signal projection and is labeled
      `coverage_measured = false`.
    - **`measured = true` is granted only to the live call that just happened.**
      Replaying a recorded usage snapshot travels the same scoring path but is
      labeled `provenance = recorded` · `measured = false` — a captured measurement,
      not a new one.
    - **The default path never sends.** The Azure SDK is an **optional dependency**,
      lazily imported only when you construct an `AzureModelRouterClient`. Otherwise
      it is an injectable seam (like the metrics emitter), so the CLI, CI, and tests
      stay pure-standard-library and deterministic.

!!! tip "The measurement we actually ran — [experiment 09](../lab-notebook/09-live-routing-proof.md)"
    Sending curated prompts to a real Foundry Model Router through this bridge, a
    single `model-router` deployment actually branched to **`gpt-5.4` (3) and
    `grok-4-1-fast-reasoning` (2)** — the repository's first `measured = true`
    measurement snapshot (keyless Entra). For the per-task evidence and the honesty
    boundary see [experiment 09 · live routing](../lab-notebook/09-live-routing-proof.md).

## 1. Handling the Foundry config

The environment variables the live bridge reads. Each accepts both the
Foundry-specific name and the generic Azure OpenAI name; if any is missing,
everything stays offline.

| Variable | Role | Alternate name |
| --- | --- | --- |
| `AZURE_AI_FOUNDRY_ENDPOINT` | Resource endpoint | `AZURE_OPENAI_ENDPOINT` |
| `AZURE_AI_FOUNDRY_MODEL_ROUTER` | Model Router deployment name | `AZURE_MODEL_ROUTER_DEPLOYMENT` |
| `AZURE_AI_FOUNDRY_AUTH` | Auth method (optional): `entra` \| `key`, auto if empty | — |
| `AZURE_AI_FOUNDRY_API_KEY` | API key — **not needed with Entra ID** | `AZURE_OPENAI_API_KEY` |
| `AZURE_AI_FOUNDRY_TOKEN_SCOPE` | Entra token scope (optional, default Cognitive Services) | — |
| `AZURE_AI_FOUNDRY_API_VERSION` | Data-plane API version (optional) | `AZURE_OPENAI_API_VERSION` |
| `AZURE_AI_FOUNDRY_CONNECTION_STRING` | Observability transport (optional) | `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| `FOUNDRY_PRICING_PATH` | Your tenant's rate YAML (optional) | `COST_ROUTER_PRICING` |

There are two ways to authenticate. With an **API key** present it uses key auth;
without one it switches automatically to **Microsoft Entra ID (Azure AD)** token
auth. On a resource with key auth disabled (`disableLocalAuth=true`, common in
enterprise tenants) the latter is the only path — for the full procedure see
[1-bis. Microsoft Entra ID (keyless) auth](#1-bis-microsoft-entra-idkeyless).

Copy `.env.sample` to `.env` and fill it in locally (`.env` is gitignored). The
`cost-router foundry status`/`live` commands **auto-load this `.env`** on run and
then read the config — no separate `source` or `export` needed; it just works. The
rules are deliberately conservative:

- With **no `.env`, nothing happens** (harmless). CI and default runs have no `.env`,
  so they stay offline and deterministic.
- **A real environment variable already exported in the shell always wins** (`.env`
  never overwrites it). CI settings and explicit exports are never silently replaced.
- It reads only `KEY=VALUE` lines. Blank lines, `#` comments, and a leading `export`
  are ignored, and quotes around the value are stripped. There is no shell expansion
  or command execution at all (values are taken literally).

To use a different file, pass `--env-file <path>` (default `.env`). You can check
what is wired **without exposing secrets**:

```bash
cost-router foundry status
```

```text
Azure AI Foundry — live measured Model Router bridge
  router configured : yes
  credentialed      : yes
  auth method       : API key                          # or Microsoft Entra ID (keyless)
  endpoint          : https://your-resource.example   # host only (path/query removed)
  deployment        : model-router
  api key           : set (****WXYZ)                            # last 4 only
  connection string : missing
  pricing           : (bundled illustrative — measured=false)
  .env loaded       : 3 setting(s) from .env                    # count auto-loaded (values hidden)
  ready: `cost-router foundry live --live` (needs a workload with prompts).
```

!!! warning "Secrets never appear in the clear"
    `status()` reduces the endpoint to **scheme+host** and masks the API key and
    connection string to their **last 4 characters**. Only the deployment name and
    API version (not secrets) are shown as-is, so it is safe to paste into logs or on
    screen. It can also be machine-read with `--json`.

### 1-bis. Microsoft Entra ID (keyless) auth {#1-bis-microsoft-entra-idkeyless}

Enterprise tenants often turn off API-key auth (`disableLocalAuth=true`). Then,
instead of a key, you call with a bearer token issued from **your Azure identity**
(`az login`, a managed identity, environment credentials, and so on). The bridge
**switches to Entra ID automatically when there is no API key**, so the setup is
essentially "leave the key blank."

```bash
# 1) install the live extra (openai + azure-identity)
pip install "foundry-cost-router[foundry]"

# 2) grant your identity the data-plane role — once, on the resource
az role assignment create \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --role "Cognitive Services OpenAI User" \
  --scope "<resource resourceId>"

# 3) log in (sandbox/headless uses --use-device-code)
az login --use-device-code

# 4) .env: leave the key blank, endpoint+deployment only (+ pin the method if you like)
#    AZURE_AI_FOUNDRY_ENDPOINT=https://your-resource.example    # your real resource host
#    AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router
#    AZURE_AI_FOUNDRY_AUTH=entra        # optional — auto entra when there is no key
cost-router foundry status              # auth method : Microsoft Entra ID (keyless)
```

- **Role**: a data-plane call needs `Cognitive Services OpenAI User` (the admin role
  *Contributor* cannot make inference calls).
- **Scope**: the default token scope is
  `https://cognitiveservices.azure.com/.default`, overridable with
  `AZURE_AI_FOUNDRY_TOKEN_SCOPE`.
- **Forcing**: to force keyless in an environment where both key and Entra are
  possible, set `AZURE_AI_FOUNDRY_AUTH=entra`.
- **Determinism preserved**: `azure-identity` is lazily imported only on a live call —
  the default offline path and CI work without the package.

!!! note "It handles no secrets"
    The Entra path has no key to put in `.env` in the first place. The token is issued
    from your identity at the moment of the live call and exists only in memory; this
    repository stores no credential of any kind.

## 2. The measured scoring path

The heart of it is feeding `pricing.cost_usd(model, tokens)` the **response's real
usage instead of the synthetic `task.tokens`**. That one spot is the only difference
between an offline arm and the live bridge.

```python
from router.foundry_live import RouterOutcome, measured_router_summary

# one task's real outcome: the model the router picked + the tokens billed
outcome = RouterOutcome(
    model="gpt-4o",
    usage={"input": 1000, "cached": 200, "output": 180, "reasoning": 120},
    provenance="live",
)

summary = measured_router_summary(
    workload, signals, policy, pricing,
    client=my_client,                     # each task -> RouterOutcome
    grader=my_grader,                     # optional: with one, coverage_measured=true
    model_aliases={"gpt-4o": "balanced-pro"},  # real name -> rate/signal key
)
# summary["labels"] = {measured, spend_source: "provider-usage", provenance,
#                      coverage_measured, coverage_basis}
```

- **Cost** is computed from `outcome.usage` with `pricing`. The usage is measured, but
  the amount for a call routed through the `model-router` deployment is **incomplete —
  missing the router input markup** (see `†` below).
- **Coverage** is measured when a `grader` is present (`coverage_basis = "graded"`);
  without one it is that model's offline signal projection (`"offline-projection"`).
  The captured **real model** has no matching row in the offline signals, so coverage
  is honestly **ungraded** (`coverage = null`, `coverage_basis = "ungraded"`) — the
  usage is measured but the accuracy is not.
- **`measured`** is `true` only when every outcome's provenance is `live`.
- **`model_aliases`** maps a vendor name like `gpt-4o` to a rate/signal key.

## 3. Running live

Even without credentials you can replay a **recorded usage snapshot** to see the
scoring path (the default). This snapshot
(`samples/responses/model-router-usage.sample.json`) is **real output captured from a
genuine Azure Model Router call** — it contains the models the router actually picked
(`gpt-5.4` · `grok-4-1-fast-reasoning`) and the real billed tokens. Because it is a
replay it is honestly labeled `provenance = recorded` · `measured = false`, and the
real models have no matching row in the offline signals, so coverage is **ungraded**:

```bash
cost-router foundry live
```

```text
Azure Model Router — measured usage  (recorded snapshot (…/model-router-usage.sample.json))
  tasks             : 5
  routed cost†      : $0.02              # captured real usage costed at the 5-series rates
  avg $/task†       : $0.0041
  coverage          : ungraded (ungraded — usage is measured, correctness needs a grader)
  spend source      : provider-usage
  provenance        : recorded
  measured          : no                 # a replay, so measured=false
  † Model Router-derived cost omits the router input-token markup component. Retained as historical output; not publishable and not usable for a savings claim.
  → this is a replay/projection; run with --live + credentials for measured=true.
```

!!! danger "`†` — the router-derived amount is **incomplete**"
    Model Router billing is synthetic: the **router input-token markup** + the input
    and output of the chosen sub-model. The rate card has no markup line item, so the
    amount for a routed call is **missing one billed component** — not an
    approximation, but incomplete. Show the amount as history, but never use it in a
    cost or savings claim; the CLI **enforces this footnote directly**: if it cannot
    read the versioned annotation
    [`samples/annotations/legacy-router-pricing.annotation.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/annotations/legacy-router-pricing.annotation.json)
    or the hash is off, it **fails closed** with a stricter wording. Token usage,
    model selection, latency, and auth are valid independently of this defect, and an
    arm that calls a single deployment directly is unaffected.

### Re-capture the recorded snapshot from real Azure — `--capture`

The recorded snapshot this repository ships is not a hand-written mock but a
**capture of real router output**. `capture_recorded_usage`, the inverse of
`load_recorded_usage`, runs the live client over a workload that has prompts and
records the genuine `task_id -> {model, usage}`. Re-capture it in one CLI line
(credentials + `--live` required; without `--live` it refuses and writes nothing):

```bash
cost-router foundry live --live --capture samples/responses/model-router-usage.sample.json
```

```text
foundry live — captured 5 real outcomes → …/model-router-usage.sample.json
  source     : LIVE Azure Model Router (model-router)
  captured_at: 2026-…Z
  models     : gpt-5.4×3, grok-4-1-fast-reasoning×2
  labels     : measured=false  provenance=recorded  captured_from=live
  replay     : cost-router foundry live --recorded …/model-router-usage.sample.json
```

- Each entry's model name is normalized (`gpt-5.4-2026-03-05` → `gpt-5.4`) so it
  matches a stable rate row. Each entry is stamped `provenance = recorded` (a capture
  is a *recording*, so a replay does not masquerade as a new measurement), and the
  file-level `captured_from = live` label records "the source was genuinely live."
- Secrets and endpoint URLs are never stored in the snapshot — only non-secret
  provenance (account name · resource group · region · API version) remains in the
  `resource` block.

### Curated tasks as measurements — one command (t-0001–t-0006)

The bundled telemetry has no prompts, so it cannot be sent live. That is why we
prepared a workload that carries the arena's five curated tasks **with sendable
prompts**: `samples/telemetry/curated-arena-live.sample.jsonl`. Once your credentials
are in place, this one command turns **all** of t-0001–t-0006 into real Model Router
calls with `measured = true`:

```bash
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/your-tenant.yaml \
  --store    runs.jsonl
```

```text
Azure Model Router — measured usage  (LIVE Azure Model Router)
  tasks             : 5
  routed cost†      : $…                 # usage your deployment actually billed × the rate card
  avg $/task†       : $…
  coverage (projected): …                # offline signal projection with no grader
  provenance        : live
  measured          : yes                # a live call that just happened
  † Model Router-derived cost omits the router input-token markup component. …
```

If you have no credentials yet, you can run **the same workload as a recorded
snapshot** to see the path exactly (deterministic, no send, `measured = false`):

```bash
cost-router foundry live --workload samples/telemetry/curated-arena-live.sample.jsonl
```

!!! note "Why only this workload can be sent live"
    The bundled telemetry (`mixed-coding-workload…`) has only `task_id` · `tokens` and
    **no prompt text**, so it cannot be sent to a real endpoint. `curated-arena-live…`
    attaches **authored synthetic prompts** (input for display and sending,
    `measured = false`) to the arena's five tasks so that a live send is possible. The
    prompts are authored-synthetic, but the usage and cost from **actually sending them
    is measured = true** — the source of the input (authored) and the source of the
    measurement (live) are separate things. To measure accuracy (pass/fail) too,
    inject a `grader` (without one, coverage is labeled an offline signal projection).

### With an arbitrary workload

You can also hand it a workload with your own real prompts directly:

```bash
cost-router foundry live --live --workload my-prompts.jsonl --pricing samples/pricing/your-tenant.yaml
```

## 4. Wiring into the historical dashboard

Pass `--store` and the measured run is recorded as one line in the existing metrics
history, which the web app's **Historical dashboard** panel and `metrics history`
read directly:

```bash
cost-router foundry live --store runs.jsonl
cost-router metrics history --store runs.jsonl
# 2026-…Z  foundry-live cov=0.0% routed=$0.020334 …   # cov=0.0% = ungraded, measured=no
#                                    ↑ router-derived amount — pricing incomplete (see † above)
```

The row carries the `measured` flag and the `provenance` · `spend_source` dimensions,
so a live measured run and an offline projection are honestly distinguished on the
same dashboard.

## 5. The real Azure client

`AzureModelRouterClient` calls the deployment over the standard chat-completions
surface and reads the response's `model` (the sub-model the router chose) and `usage`
(the tokens billed). The SDK is lazily imported in `_sdk_client()`, so importing this
module does not require the SDK. To install the live extra:

```bash
pip install "foundry-cost-router[foundry]"   # openai + azure-identity
```

Auth follows `config.auth_method`:

- **Key auth** — `AzureOpenAI(api_key=…)`. Selected automatically when
  `AZURE_AI_FOUNDRY_API_KEY` is present.
- **Entra ID (keyless)** — with no key, it builds an `azure_ad_token_provider` via
  `azure.identity.DefaultAzureCredential` and calls with
  `AzureOpenAI(azure_ad_token_provider=…)`. `azure-identity` is lazily imported only
  at this moment.

```python
from router.foundry_live import AzureModelRouterClient, FoundryConfig

# with no key, auth_method == "entra" — a token issued from the az login identity
client = AzureModelRouterClient(config=FoundryConfig.from_env())

# test/offline: to verify the Entra branch with no network or azure-identity,
# inject a token_provider (or sdk_client / RecordedRouterClient).
client = AzureModelRouterClient(
    config=FoundryConfig.from_env(),
    token_provider=lambda: "fake-bearer-token",
)
```

In tests and offline, inject an `sdk_client` (or `RecordedRouterClient`) to run the
whole path with no network.

!!! tip "Relationship to the Honesty Charter"
    This bridge is the code that actually fills in the *"a live eval on your tenant →
    `measured = true`"* row of the [Honesty Charter](../honesty.md). The amount gets
    closer to your range only when you put **your real rates** in
    `samples/pricing/your-tenant.yaml` (gitignored) — the router-derived amount stays
    incomplete, separately, until the markup line item is filled in.
