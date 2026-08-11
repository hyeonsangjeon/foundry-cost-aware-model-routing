# Glossary — metrics and experiment arm labels

A single place to pin down the metrics used across this repo. In particular,
**pass rate** and **grading coverage** sound alike but are **two different
metrics**.

## Experiment arm labels

An **arm** is one comparison strategy evaluated against the same workload under the same
measurement plan.
Experiments 11, 12, and the 03D measured result use these four identifiers:

| Label | Meaning |
| --- | --- |
| `router-cost` | Model Router in Cost mode |
| `router-balanced` | Model Router in Balanced mode |
| `router-quality` | Model Router in Quality mode |
| `direct-premium` | Calling the premium model directly · `gpt-5.6-sol` |

On the offline projection page for experiments 01–08, `direct-premium` names the synthetic
premium-on-every-task baseline. It is not measured performance for `gpt-5.6-sol`.

!!! abstract "At a glance — the two metrics differ"
    | Metric | Meaning | Denominator |
    | --- | --- | --- |
    | **pass rate** | Share of tasks that passed (were solved) | Number of **tasks** attempted |
    | **grading coverage** | Share of **cells actually graded** (measurement completeness) | Number of planned **cells** (task × arm × sample n) |

    **Where** — pass rate applies to **every experiment and 03D**; grading coverage only to the **measured experiments (11 · 12 · 03D)**.

> **The one sentence to remember.** Within the same experiment, **pass rate** and
> **grading coverage** can come out different — not a typo, but **separate metrics
> with different denominators**.

!!! tip "Reading rules"
    - When a measured result (11 · 12 · 03D) reports "the share of cells graded,"
      always call it **grading coverage**. Never place the bare word "coverage"
      next to a pass rate.
    - "The share of tasks that passed" is always the **pass rate**.
    - In the offline experiments and the CLI, `coverage` (= `accepted / counted`)
      is the same value as the **pass rate**.

??? example "Example (03D measured) — if you want the actual figures"
    The concepts are enough on their own, but if you want concrete numbers: the
    offline experiments have no timeouts, so grading coverage is effectively
    **100%** and matches the pass rate. In the 03D measured run, by contrast,
    `router-cost` splits into a **pass rate of 95.8% (23/24)** and **grading
    coverage of 94.4% (68/72)** — because the denominators differ: **24** tasks
    versus **72** cells. (For the aggregate grading coverage, the cell definition,
    and the gate floor, see "Precise definitions per term" below.)

??? note "Why the two diverge — same offline, different when measured (the timeout mechanism)"
    The two metrics **count different units**.

    - **Pass rate counts by task** — "Did it solve that problem?"
    - **Grading coverage counts by cell** — "Did an answer even arrive to grade?"

    The offline, deterministic experiments have no timeouts, so every cell has a
    body to grade and grading coverage **matches** the pass rate. That is why the
    offline CLI calls the pass rate by the single word `coverage`.

    In a measured run it is different. When one cell times out:

    - there is no body to grade, so it **drops out of grading** (grading coverage ↓,
      counted by cell), and
    - if that timeout keeps the task from ever being accepted as a pass, it is also
      **counted as a failure** (pass rate ↓, counted by task).

    The same single timeout registers at different magnitudes on the **cell**
    (grading coverage) and the **task** (pass rate), so the two metrics diverge.

??? note "Precise definitions per term — code and sealed fields"
    **Pass rate.** Of the tasks attempted, the share **accepted as a pass
    (solved)** because their verifiable execution signals were clean. It answers
    "how much did this arm actually solve?"

    - **Offline experiments (01–08).** The code computes `coverage = accepted /
      counted` (`src/router/baseline.py`). So the `coverage` field emitted by the
      offline CLI and the experiment contract (`min_coverage`) is **the same value
      as the pass rate**. The **"coverage cliff"** narrative in the lab notebook
      (experiments 03, 07, and so on) refers to this same pass rate.
    - **Measured experiment (03D).** The `pass_rate` field in the sealed snapshot —
      e.g. `router-cost` is **23/24 = 95.8%**.

    **Grading coverage.** A **cell** is (task × arm × sample) — each task·arm
    combination is measured **n times** (n=3 in 03D). Grading coverage is the share
    of planned cells that had a response body and were **actually graded**. It
    answers not quality or pass/fail but **how complete the measurement was**
    (measurement completeness).

    - **Only meaningful in measured runs.** It is the `coverage` field in the sealed
      snapshot (`basis: graded`), i.e. `graded_cells / planned_cells` — for 03D,
      **24 tasks × 4 arms × n=3 = 288 cells**, giving an aggregate **277/288 =
      96.18%** and an arm low of **68/72 = 94.4%**.
    - Low grading coverage does not mean "the code was wrong"; it means **there was
      no body to grade in the first place** (e.g. a timeout). That is why the
      quality gate keeps a separate grading-coverage floor (≥ 90%).

??? note "Labels you will see alongside these"
    | Label | Meaning |
    | --- | --- |
    | `measured=false` (projection) | Offline calculation over synthetic data. Not measured Azure spend (experiments 01–08). |
    | `measured=true` (measured) | Value measured from real Azure Foundry calls and usage (experiments 09 · 10 · 11 · 12). |
    | `evidence_tier=directional` | 24 tasks · single tenant · one measurement — a directional signal, not statistical confidence. |
    | `cost_complete=true` / `unpriced 0%` | Every cell priced at pinned rates. |
    | `plan_hash` | Content-addressed hash sealing the workload, policy, and rates. The reference point for reproduction and replay. |

    Check each figure's honesty label (measured/projected) **on its own page** — this
    glossary only unifies the names and definitions; it does not replace the per-page
    claim boundaries. For the boundaries as a whole, see the
    [Honesty Charter](../honesty.md).
