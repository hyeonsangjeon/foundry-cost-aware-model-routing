# Fleet registration & model selection · Fleet

The measured arena (`cost-router foundry arena`) and the dashboard run **four
strategy arms** — **router (the main one)**, **cheapest (the floor)**, **premium
(the ceiling)**, and **ensemble (the fan-out)**. Which **real deployed model** backs
each arm used to be hardcoded in the code. `src/router/fleet.py` promotes that
mapping into a small **environment file (the fleet config)** that you own — this is
exactly the "register the models you will use in an environment file" step.

!!! note "Fleet = catalog + role assignment"
    - **Catalog**: the list of models you have actually deployed. Each entry has the
      logical `name` used in the pricing table and reports, the Azure `deployment`
      name the live client calls, and a free-form `tier`.
    - **Role assignment (slate)**: which catalog model backs which arm. `name` and
      `deployment` are usually the same, but they are **deliberately separate** so a
      single logical model can point at a differently named deployment.

## 1. The fleet config file

```yaml
# samples/fleet/foundry-5series.fleet.yaml
version: 1
models:
  - { name: gpt-5.4-nano, deployment: gpt-5.4-nano, tier: small,    label: "GPT-5.4 nano — cheap floor" }
  - { name: gpt-5.4-mini, deployment: gpt-5.4-mini, tier: mid,      label: "GPT-5.4 mini — mid tier" }
  - { name: gpt-5.4,      deployment: gpt-5.4,      tier: frontier, label: "GPT-5.4 — frontier ceiling" }
  - { name: model-router, deployment: model-router, tier: router,   label: "Foundry Model Router" }
roles:
  router: model-router
  cheapest: gpt-5.4-nano
  premium: gpt-5.4
  ensemble: [gpt-5.4-nano, gpt-5.4-mini, gpt-5.4]
```

How to point a run at this file (highest precedence first):

1. The `--fleet PATH` flag
2. The `FOUNDRY_FLEET_PATH` (or `COST_ROUTER_FLEET`) environment variable — auto-loaded if you put it in `.env`
3. The bundled sample `samples/fleet/foundry-5series.fleet.yaml`
4. The in-code default (always works even with no file at all — preserving offline determinism)

Change `deployment` to the name your resource actually has, and match `name` to the
row in the pricing YAML.

### 1-1. `provider` — which call surface to use (multi-provider)

A **single** Foundry (`kind=AIServices`) resource hosts both Azure OpenAI models and
partner/OSS models on the **same endpoint**. The **wire path (surface)** the actual
call goes out on, however, splits in two. A catalog entry's `provider` field picks
between them:

| `provider` | Call surface | Target models |
|---|---|---|
| `openai` (default) | Azure OpenAI chat-completions (`*.openai.azure.com`) | Model Router, GPT-5.x / GPT-4o family |
| `foundry` | Azure AI Model Inference (`*.services.ai.azure.com/models`) | DeepSeek · Mistral · xAI · Moonshot · Meta (Llama) · Cohere · MS (Phi) and other partner/OSS |

```yaml
models:
  - { name: gpt-5.6-sol,      deployment: gpt-5.6-sol,      tier: frontier }              # provider omitted = openai
  - { name: deepseek-v4-pro,  deployment: deepseek-v4-pro,  tier: frontier, provider: foundry }
```

- For the OpenAI family you can just **omit** `provider` (defaults to `openai`, and
  it stays out of the YAML too).
- The partner-surface endpoint is derived automatically from the resource name in
  `AZURE_AI_FOUNDRY_ENDPOINT` (`https://<resource>.services.ai.azure.com/models`).
  If it differs, override it with `AZURE_AI_FOUNDRY_INFERENCE_ENDPOINT`. Auth uses
  the **same Entra ID (keyless)** credential as the OpenAI surface.
- A real example that registers all 13 deployments (OpenAI 5 + partner 7 +
  embedding) is `samples/fleet/foundry-ext-full.fleet.yaml` (pricing at
  `samples/pricing/foundry-ext-full.yaml`). The **surface** column of
  `cost-router models list` shows at a glance which surface each model uses.

!!! note "Rate-card schema — offline is v1, bench/paid is v2 (fail-closed)"
    The `samples/pricing/foundry-ext-full.yaml` above is the **v1** pricing table
    that offline experiments use. The `benchmark`/paid-measurement path, by contrast,
    bills with a **v2 rate card** (`schema_version: 2`; e.g.
    `samples/pricing/foundry-ext-router.yaml`) — its core is a synthetic formula that
    adds an input-token markup on the router arm, plus a **fail-closed** rule that
    seals any backend with no rate as unpriced instead of filling it with an
    arbitrary rate. For the path split between the two schemas see
    [measurement protocol §6.1](measurement-protocol.md#61-v1-vs-v2).

!!! note "Where the `provider` tag matters"
    The Model Router arm already routes many of these partner models **cross-provider,
    internally** (no separate deployment needed —
    [experiment 07](../lab-notebook/07-model-router.md)). So this `provider` tag
    matters when an arm that calls **directly** without going through the router —
    cheapest · premium · ensemble fan-out — calls a partner surface. Multi-provider
    routing itself is a built-in feature (table stakes), and this repository's value
    sits on the validation · ensemble · governor · audit axes above it.

!!! warning "`provider: foundry` is scoped out of benchmarks (retiring SDK, 2026-08-26)"
    The partner surface (`provider: foundry`) runs on the beta SDK
    `azure-ai-inference`. That SDK has a **documented retirement on 2026-08-26**, so
    BOLT-03B **scoped it out rather than migrating it** — the golden path (Model
    Router + the direct gpt-5.x arms) is already the `openai` v1 surface, and the
    partner arm enters no benchmark arm, so migrating would only widen the scope
    without changing the measured result. This scope-out is **enforced in code**: if a
    `provider=foundry` arm enters benchmark mode or a publishable path,
    `router.foundry_live.assert_provider_benchmark_safe` blocks it fail-closed
    (opt-in wiring smoke tests are still allowed). To carry a measured cost claim
    before retirement, you must first move to the OpenAI v1 surface.

## 2. Select in the terminal (the `/model` picker)

Look at the catalog and pick which model goes in each arm. The selection is saved to
the gitignored `.foundry-fleet.local.yaml`, so real deployment names are never
committed.

```bash
cost-router models list            # catalog + current slate + live-readiness
cost-router models show            # just the resolved role -> deployment
cost-router models select          # interactive: enter a number or a name per arm (/model style)
```

Non-interactively (scripts · CI) you specify it directly with flags:

```bash
cost-router models select \
  --router model-router --cheapest gpt-5.4-nano \
  --premium gpt-5.4 --ensemble gpt-5.4-nano,gpt-5.4-mini,gpt-5.4
```

After saving, run **the slate you chose** as a measurement:

```bash
cost-router foundry arena --fleet .foundry-fleet.local.yaml --live
```

## 3. Select from the dashboard

Bring up the dashboard with `cost-router serve` (or `cost-router hero --serve`) and
the **"Fleet & live routing"** panel shows the same catalog — router/cheapest/premium
dropdowns and an ensemble checkbox. Press **Run selection** and it replays the
committed **measured snapshot** and prints the exact terminal command to measure your
selection live.

!!! danger "Honesty boundary — the web path never makes a paid call"
    The dashboard's `Run selection` makes no new Azure call. It replays the committed
    measured snapshot, **honestly re-labeled `measured = false` ·
    `provenance = recorded`** (a captured measurement, not a new one). So choosing a
    different slate
    in the web does not change the offline numbers — they reflect the captured
    **reference fleet**, which is spelled out in the response's `note` and
    `recorded_fleet`. To **actually measure your selection**, use the terminal command
    (`... --live`) the panel printed.

## 4. If you have only one deployment

A head-to-head usually spans several deployments, but even with a single deployment
you can prove the **entire live path** end to end (keyless Microsoft Entra ID → real
call → real token usage → pricing → hash-chained ledger). Point every arm at that one
deployment and the arms tie — which is exactly the point: it is not a spread, it is a
genuine *measured* smoke test.

```bash
cp samples/fleet/single-deployment.example.yaml my-fleet.local.yaml
# edit deployment in my-fleet.local.yaml to your resource's name
cost-router foundry arena --fleet my-fleet.local.yaml --live --max-output-tokens 512
```

## 5. Use it as a library

```python
from router.fleet import FleetRegistry

reg = FleetRegistry.resolve()                       # --fleet/env/bundled/default precedence
reg = reg.with_roles(premium="gpt-5.4-mini")        # swap a role (validated, immutable)
slate = reg.slate()                                 # the FleetSlate the live arena consumes
print(reg.validation_errors())                      # [] means valid
```

`FleetRegistry` is immutable, so `with_roles(...)` returns a validated new registry —
the CLI and dashboard selection flows never touch shared state.
