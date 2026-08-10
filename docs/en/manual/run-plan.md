# Resolved Run Plan

When preview, human approval, run, ledger, and replay **each interpret their own settings
separately**, what you approved and what you ran can drift apart. 03A closes that gap. It
resolves a single local config file **once** and seals it into an **immutable object** called
`ResolvedRunPlan`, and all five paths above read that same object. The plan carries a
deterministic `plan_hash`, and approval is bound to that hash. The cockpit is now wired to
this plan too — `cost-router dashboard --live --config <file>` binds the canonical
`ResolvedRunPlan` as the cockpit's single source of truth, so preview, approval, run, abort,
and replay all key off the same `plan_hash` (03C, §9). The cockpit reuses 03B's shared abort
gate and spend ledger rather than building a separate cancel or budget path.

This page describes the canonical plan that `src/router/run_plan.py` builds and the CLI that
handles it.

!!! note "The plan itself is offline"
    `benchmark plan` **sends nothing**. It reads only the local config and the workload and
    rate-card files it points to, fingerprints them, prints the plan **redacted**, and
    computes the `plan_hash`. A real Azure call happens only when `--live` carries a
    **matching `--approve-plan`**, and even then only in a separate seam (the [live
    bridge](foundry-live.md)).

## 1. The three commands

```bash
# 1) Create a local config from the committed template (no credential fields).
cost-router config init                       # → .foundry.local.yaml

# 2) Resolve, redact, and hash the plan. Zero sends.
cost-router benchmark plan --config .foundry.local.yaml

# 3) A human reviews the plan, then approves with the printed hash and runs.
cost-router benchmark run  --config .foundry.local.yaml \
    --live --approve-plan sha256:<...>
```

The template `config init` copies is `foundry.example.yaml` at the repository root.
`.foundry.local.yaml` is gitignored and **never holds credentials** — the keys `api_key`,
`access_token`, `bearer_token`, `client_secret`, `password`, `connection_string`,
`sas_token`, and `secret_key` are rejected at parse time. For authentication, keyless
Microsoft Entra ID (`az login`) is the golden path.

## 2. `plan_hash` — what changes the hash, and what doesn't

`plan_hash` is a SHA-256 computed over **only the fields that affect cost, quality, and
execution**, normalized (sorted-key, tight JSON). The principle is simple.

| Changing it **changes** the hash | Changing it **leaves** the hash unchanged |
| --- | --- |
| `run_mode`, arms (deployment · kind · provider), workload fingerprint | `display.locale` / `--locale` / server locale |
| rate-card fingerprint, `budget_usd`, approval basis (ceiling/rate) | purely presentational settings |
| `max_output_tokens`, `repetitions`, `retry.max_retries` | |
| endpoint (host only), `api_version`, `random_seed` | |

In other words, **change something that moves cost/quality/execution and the hash moves with
it**; change something purely presentational and it stays put. This two-way contract is
pinned by a regression test (`tests/test_live_config.py`).

!!! warning "The endpoint is redacted to host only"
    The endpoint that enters the plan is reduced to `scheme://host[:port]`, stripping the
    path, query, and any in-URL credentials (userinfo). `http://` and credentials embedded in
    the URL are rejected. So the printed redacted plan alone is enough to reproduce the
    `plan_hash` exactly.

### Resolution precedence

Execution fields resolve in the order `CLI override > local YAML > legacy env > safe
default`, and each field's origin is recorded in the plan's `sources` map (secrets are never
recorded). Only locale is a §12 exception, following `--locale > COST_ROUTER_LOCALE >
display.locale > en` and having **no effect whatsoever on execution semantics** (the behavior
is merely reserved for i18n).

## 3. The approval screen — planned cells and the transport-attempt range

The human approval screen shows the **number of planned cells** and, per cell, the
**base/max transport attempts**.

```
— approval summary —
  planned cells   : 12
  transport attempts / cell : base 1, max 4
      (retries may dispatch anywhere in [base, max] — not an exact call count)
  worst-case reservation : $0.10 (whole ceiling reserved before dispatch)
  approve with    : --approve-plan sha256:<...>
```

It does not call a retriable call **"exactly N times."** A throttled cell may legitimately
dispatch anywhere between `base` and `max` (`max = 1 + retry.max_retries`). `planned cells =
task count × repetitions × arm count`.

!!! danger "Approval is bound to the hash — a mismatch fails closed"
    A `--live` run requires `--approve-plan <plan_hash>`, and if that value differs from the
    freshly resolved plan's `plan_hash` **by even one character, it is rejected before
    dispatch** (exit 1). Credentials are looked up only afterward. So a stale or mismatched
    approval sends no paid call whatsoever.

## 4. The Model Router arm is explicit and cannot vanish

Arms resolve from the **explicit `arms:` list** in the local YAML. The `model_router` arm is
one item on that list, so it **can never be dropped** by a path that "only reads the ensemble
role." The candidates the plan builds and the candidates in the sealed manifest always carry
the same arms.

## 5. Single source of truth — preview = approval = run = manifest = replay = cockpit

The same `plan_hash` runs through six points.

1. **Preview**: `benchmark plan` prints the redacted plan + hash.
2. **Approval**: a human confirms that hash with `--approve-plan`.
3. **Run**: the runner measures with the plan's candidates, rates, and budget.
4. **Manifest**: the sealed snapshot records the same `plan_hash`.
5. **Replay**: `replay` reads the manifest's `plan_hash` back verbatim.
6. **Cockpit**: `dashboard --live --config` binds the same plan, so preview, approval, run,
   abort, and snapshot are all bound to the same `plan_hash` (03C). The browser never supplies
   plan content; it only steers the server-side plan.

This identity is verified with a scripted offline client, so CI never sends.

## 6. The legacy config path is deprecated

The earlier per-command env/flag configuration (`foundry live`, `foundry arena`, `measure
run`, `measure catalog`) **still works but is deprecated**. Those paths have their own
independent resolution semantics that the canonical plan now owns, so calling them prints
guidance to stderr. `dashboard --live` run without `--config` prints the same deprecation
warning, for the same reason — a cockpit that hasn't bound a plan falls back to the legacy
ad-hoc config path.

```
note: `cost-router foundry live` uses the legacy environment/flag config path,
deprecated by BOLT-03A in favor of the canonical run plan
(`cost-router config init` then `cost-router benchmark plan --config
.foundry.local.yaml`). See docs/manual/run-plan.md.
```

The warning goes only to stderr, so it never pollutes `--json` stdout or a captured summary.
Use the canonical plan path for new work.

## Related documents

- [Live measured bridge](foundry-live.md) — the seam for real Azure Model Router calls.
- [Fleet registration & model selection](fleet.md) — the artifacts that become arms/rate cards.
- [Audit ledger](ledger.md) — sealed snapshots and replay integrity.
- [Experiment config (YAML)](experiments.md) — the experiment-artifact schema.
