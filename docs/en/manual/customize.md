# Customization guide — swap in your own workload (D13)

This repository was built on one premise: **run it on your own Foundry, as is**.
To do that you only change five places. Each one is a separate file, so you swap
configuration without touching code. The `measured = false` projections run
offline, right away; the `measured = true` measurements run after you set up `.env`
+ `az login` and press the approve button in the
[local cockpit](../lab-notebook/09-live-routing-proof.md).

## The five places you change

### 1. Prompts (`system_prompt` / `user_prompt`)
- **Where:** the workload JSONL — `samples/telemetry/<name>.jsonl`. You attach the
  prompt fields to a task row.
- **Schema (one task):**
  ```json
  {"task_id": "t-0001", "class": "generate",
   "system_prompt": "You are a terse senior engineer.",
   "user_prompt": "Write a Python function `solve(n)` returning the n-th prime.",
   "validation": {"type": "regex", "pattern": "def\\s+solve"}}
  ```
- **Selection:** the experiment YAML's `dataset.workload` names which file to use
  (`experiments/*.yaml`).
- With no prompts (telemetry rows only) you cannot call a real model, so you get
  **offline projections only**.

### 2. Validation rules (`validation`)
- **Where:** the `validation` block on the same task row. `router.validation`
  judges it mechanically.
- **Rule types:** `contains` · `not_contains` · `equals` · `regex` · `nonempty` ·
  `json_valid`, plus `all` / `any` to combine them. **No subjective verdicts ("pass
  if it looks good")** — they are all pure functions over the output string.
  ```json
  {"type": "all", "rules": [
    {"type": "contains", "value": "def solve"},
    {"type": "not_contains", "value": "TODO"}
  ]}
  ```
- If a rule is wrong (unknown type, bad regex) `validate_rule` **fails loudly
  before the run**.

### 3. Fleet (candidate models)
- **Where:** `samples/fleet/*.fleet.yaml` (e.g. `foundry-ext-full.fleet.yaml`,
  `foundry-5series.fleet.yaml`).
- **Selection:** `FOUNDRY_FLEET_PATH` (or `COST_ROUTER_FLEET`) in `.env`.
- Defines which deployment each arm (cheapest/premium/router/ensemble) calls and
  what the provider is.

### 4. Pricing
- **Where:** `samples/pricing/*.yaml` (e.g. `foundry-ext-full.yaml`; for your own
  tenant, copy `your-tenant.example.yaml` and fill in real rates).
- **Selection:** `FOUNDRY_PRICING_PATH` (or `COST_ROUTER_PRICING`) in `.env`.
- `measure` honors this path so the dry-run estimate and the measured-cost
  conversion use the **same rate card**.

### 5. Repetitions · budget (`n` · budget)
- **Where:** CLI flags — `cost-router measure run --n <reps> --budget-usd <cap>`.
- `--n` is repetitions per cell (to check variance); `--budget-usd` is a **hard
  cap**. A live run is refused without `--budget-usd`, and when the cap is reached
  it stops immediately and leaves a `partial = true` snapshot.

## The five-step recipe — swap in my workload

1. **Write the workload.** One task per line in
   `samples/telemetry/my-workload.jsonl` — `task_id` · `class` · `system_prompt` ·
   `user_prompt` · `validation`.
2. **Check the validation rules.** That each `validation` is machine-judgeable
   (checked on load by `router.validation.validate_rule`). No subjective criteria.
3. **Wire it to an experiment.** Point the experiment YAML's `dataset.workload` at
   the new file (or write a new experiment YAML).
4. **Name the fleet and pricing.** Set `FOUNDRY_FLEET_PATH` · `FOUNDRY_PRICING_PATH`
   in `.env` to your deployments and rates.
5. **Preview with the catalog first, then the approved run.** Use `cost-router
   measure catalog --workload samples/telemetry/my-workload.jsonl` to see, up front,
   **the full outgoing prompts · the validation rules · the candidate models · the
   estimated tokens · the projected cost** → if it looks right, run it with
   `cost-router measure run --live --budget-usd <cap>`. If a prompt changes, the
   manifest's `workload_fingerprint` changes too, so it is **honestly recorded as a
   different experiment**.

!!! tip "Everything is visible before the run"
    You can see what goes out **before** the run — `cost-router measure catalog`
    shows the task list, each full prompt, the validation rules, the candidate
    models, the estimated tokens, and the dry-run cost on one screen (zero paid
    calls). Only after "this is what goes out now" is visible on screen does the
    (paid) live call begin.

## The browser cockpit — `cost-router dashboard --live`

If you would rather walk **the same gates in a browser** instead of the CLI, use
the local cockpit. It follows exactly the same order as the five-step recipe
(check the connection → prompts · dry-run → approve → run → snapshot), right there
in the dashboard.

```bash
az login                      # Entra credentials are read from the environment (no input field in the browser)
cost-router dashboard --live  # 127.0.0.1-only + random port + a session-token URL printed to the console
```

- **Binding.** It binds to `127.0.0.1` only and uses a random port. You must enter
  through the `http://127.0.0.1:<PORT>/?cockpit=1&token=…` URL printed to the
  console for the cockpit to open. With a missing or wrong token the `/cockpit/*`
  routes return 403, and the public (static) build has no `cockpit=1`, so the
  cockpit itself is never rendered.
- **Connection panel.** Reuses the **masked** output of `foundry status` verbatim —
  the endpoint (host only), whether Entra login is present, the deployment, the
  pricing file. **There is no credential input field** (read from the environment /
  `az login`). Missing items get inline guidance on "what to set and how."
- **Prompts · dry-run.** Shows the full outgoing prompts · validation rules ·
  candidate models · projected cost before the run (zero paid calls). It is the same
  catalog as the CLI's `measure catalog`.
- **Approve and run.** Only after you enter the budget cap and press `Approve and
  run` does the (paid) sweep begin — that button is the **human approval gate** of
  BOLT-01 §8. If any of credentials · budget · approval · prereg is missing it
  honestly refuses and shows the reason.
- **Live progress · snapshot.** The progress and the cumulative-spend-vs-budget
  gauge stream, and it stops the instant the budget is reached (`partial=true`).
  When it finishes it **re-reads and renders** `results/measured/<exp>/<run-id>/`
  (the replay path is the verification).

When measurement finishes, tidy it into the shape the public mock-up consumes
(tenant rates masked; a human does the commit):

```bash
cost-router measure publish --run results/measured/<exp>/<run-id>
```
