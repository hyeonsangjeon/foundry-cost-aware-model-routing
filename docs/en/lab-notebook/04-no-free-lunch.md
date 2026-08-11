# Experiment 04 · When every task is hard, there is no saving

!!! abstract "One-line summary — 'there is no free lunch'"
    On a workload where every task is genuinely hard and **only the most expensive model passes**, routing tries all the cheap models, fails, and climbs to the top. The result is **100% coverage · 0.0% savings** — routing cost is **exactly the same** as naive (always premium). Routing does not invent savings that aren't there. All numbers are `measured = false`.

<figure markdown="span">
  ![Limits loop animation — the cheap tiers fail one after another, climbing all the way to the top](/foundry-cost-aware-model-routing/assets/gif/limits.gif)
  <figcaption>Limits loop — the cheap tiers each fail in turn, so every task ends up climbing to the top model. No saving, and honest spend.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** the moment the expectation lands — "turn routing on and it always gets cheaper, right?" — and you need to draw the **boundary** of that expectation honestly.
- **Task (what):** on 6 hand-picked hard tasks, attach offline signals where **only the top candidate passes** each task (`samples/responses/hard-tasks-signals.sample.json`) and run routing.
- **Experiment (what it tests):** that on this workload routing (1) **holds coverage at 100%** while (2) saving **0%** — that is, it honestly spends top-tier cost on hard work.

This is the **third honesty**, after experiments 01 · 02 (routing pays off) and experiment 03 (mistuning breaks coverage). Here it exposes the **boundary where the gain is zero** even when routing is used *correctly*.

## Setup — a workload where only the top passes

Each task's signals are defined for **every candidate** in the class; the cheap candidates fail their checks (`compiles=false` or `tests_pass=false`) and **only the most expensive candidate** passes them all. The router evaluates the cheap candidates first but, since none pass, escalates to the top.

- **Workload:** the 6 hard tasks in `samples/telemetry/mixed-coding-workload.sample.jsonl`
- **Signals:** [`samples/responses/hard-tasks-signals.sample.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/hard-tasks-signals.sample.json) (only the top is clean)
- **Policy · pricing:** bundled seed policy · pricing (`measured = false`)

## Run

```bash
cost-router experiment run limits
```

## Result — 0% savings, 100% coverage

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $0.24
  AFTER   cost-aware routing                   $0.24
  SAVED   $0.00  (0.0% lower)  at 100.0% coverage

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 0.0% ≥ 0.0%
  PASS  tasks: 6 ≥ 6
  PASS  savings_ceiling: 0.0% ≤ 0.0%
```

For each task the router evaluates a cheap candidate → fails → climbs to the next, and finally selects the **only candidate that passes (the top)**.

| task | class | attempts → result | chosen | cost |
| --- | --- | --- | --- | --- |
| t-0007 | plan | swift-coder ✗ · balanced-pro ✗ · **deep-reasoner ✓** | deep-reasoner | $0.05 |
| t-0036 | generate | mini-fast ✗ · swift-coder ✗ · **balanced-pro ✓** | balanced-pro | $0.01 |
| t-0032 | test | mini-fast ✗ · swift-coder ✗ · **balanced-pro ✓** | balanced-pro | $0.01 |
| t-0015 | validate | mini-fast ✗ · balanced-pro ✗ · **deep-reasoner ✓** | deep-reasoner | $0.0087 |
| t-0024 | repo_patch | swift-coder ✗ · balanced-pro ✗ · deep-reasoner ✗ · **premium-max ✓** | premium-max | $0.08 |
| t-0029 | repo_patch | swift-coder ✗ · balanced-pro ✗ · deep-reasoner ✗ · **premium-max ✓** | premium-max | $0.07 |

Total routing cost **$0.24** = naive cost **$0.24** → savings **$0.00 (0.0%)**.

## Reading this number honestly

Routing didn't "fail." Its promise is *"same coverage, lower cost,"* not *"always lower cost."* A saving appears **only when a cheap model actually passes**. When every task genuinely needs the top model, the correct choice is to **spend** that cost, and routing does exactly that — instead of shaving coverage to fake a saving (unlike [experiment 03](03-coverage-cliff.md)).

!!! success "Two-sided reproducibility contract (`max_delta_pct`)"
    This experiment's `expect` block pins **both** sides:

    - `min_coverage: 1.0` — routing must hold coverage at 100% (even if it has to spend), and
    - `max_delta_pct: 0.0` — on this workload **savings must not exceed 0%.**

    The second ceiling is a newly added guard. If some future change suddenly makes this hard workload look "cheaper" (say, a weakened signal, or a **phantom saving** from a cost-calculation bug), the `savings_ceiling` check fails and CI breaks loudly. Savings must be honest both upward and downward.

## When to use this experiment

- Before adopting routing, to honestly gauge **"will it even pay off on our workload?"** The gain depends on the **share of tasks where a cheap model passes**.
- To answer "we turned routing on — why isn't it cheaper?" with numbers: *"that isn't a failure; it's the honest result of a hard workload."*
- To set a **ceiling contract** in CI so benchmarks and demos don't report **inflated savings**.

## Reproduce this experiment

```bash
pip install -e .
cost-router experiment run limits          # human-readable summary
cost-router experiment run limits --json   # machine-readable full summary + contract checks
```
