# Glossary — metrics and experiment arm labels

A single place to pin down the metrics used across this repo. In particular,
**pass rate** and **grading coverage** sound alike but are **two different
metrics**.

## Experiment arm labels

An **arm** is one comparison strategy evaluated against the same workload under the same
measurement plan. Every page in this repository uses the word in that sense, and none of
them redefines it.

The measured router-mode runs (experiments 11, 12 and 13) use these four identifiers:

| Label | Meaning |
| --- | --- |
| `router-cost` | Model Router in Cost mode |
| `router-balanced` | Model Router in Balanced mode |
| `router-quality` | Model Router in Quality mode |
| `direct-premium` | Calling the premium model directly · `gpt-5.6-sol` |

The offline experiments 01–08 use a separate set of placeholder arms — `cost`,
`balanced`, `quality` (the premium baseline), `single_call` and `cost-aware mix` — over generic model
names. Those labels describe a synthetic baseline; they are not measurements of Model
Router's Cost, Balanced or Quality modes, and the two sets must not be read as the same
arms measured twice. Where an offline page needs a name for the premium-on-every-task
baseline, call it the **premium-on-every-task baseline** (shortened to *premium baseline*
after first use on a page), not `direct-premium`: the offline baseline is not measured
performance for `gpt-5.6-sol`.

!!! abstract "At a glance — three metrics, three denominators"
    | Metric | Meaning | Numerator / denominator |
    | --- | --- | --- |
    | **pass rate** | Share of tasks that passed (were solved) | passed tasks / **tasks** attempted |
    | **grading coverage** | Share of planned cells that were actually graded (measurement completeness) | `graded_cells` / **planned cells** (task × arm × sample n) |
    | **accepted among graded cells** | Share of the graded cells that were accepted | `accepted` / **graded** cells |

    **Where** — pass rate applies to every experiment. Grading coverage and
    accepted-among-graded apply only to the measured runs (experiments 11 · 12 · 13),
    which are the only runs that can leave a cell ungraded.

> **The one sentence to remember.** Within the same experiment, **pass rate** and
> **grading coverage** can come out different — not a typo, but **separate metrics
> with different denominators**.

!!! tip "Reading rules"
    - When a measured result (11 · 12 · 13) reports "the share of planned cells that
      were graded," always call it **grading coverage**. Never place the bare word
      "coverage" next to a pass rate.
    - "The share of tasks that passed" is always the **pass rate**.
    - In the offline experiments and the CLI, `coverage` (= `accepted / counted`)
      is the same value as the **pass rate**.

??? example "Example (experiment 12) — if you want the actual figures"
    The concepts are enough on their own, but if you want concrete numbers: the
    offline experiments have no timeouts, so grading coverage is effectively
    **100%** and matches the pass rate. In experiment 12, by contrast,
    `router-cost` splits into a **pass rate of 95.8% (23/24)** and **grading
    coverage of 94.4% (68/72)** — because the denominators differ: **24** tasks
    versus **72** planned cells. (For the aggregate grading coverage, the cell
    definition, and the gate floor, see "Precise definitions per term" below.)

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
      as the pass rate**. The **"pass-rate cliff"** narrative in the lab notebook
      (experiments 03, 07, and so on) refers to this same pass rate.
    - **Measured experiments (11 · 12 · 13).** The `pass_rate` field in the sealed
      snapshot — e.g. `router-cost` in experiment 12 is **23/24 = 95.8%**.

    **Grading coverage.** A **cell** is (task × arm × sample) — each task·arm
    combination is measured **n times** (n=3 in experiments 11, 12 and 13). Grading
    coverage is the share of planned cells that had a response body and were
    **actually graded**. It answers not quality or pass/fail but **how complete the
    measurement was**.

    - **Only meaningful in measured runs.** In the published bundle it is
      `result.grading.coverage`, i.e. `graded_cells / planned_cells` with
      `basis: exec-signals` — for experiment 12, **24 tasks × 4 arms × n=3 = 288
      planned cells**, giving an aggregate **277/288 = 96.18%**. Per arm it is
      `result.coverage_by_arm[<arm>]`, whose lowest value in experiment 12 is
      **68/72 = 94.4%**.
    - Low grading coverage does not mean "the code was wrong"; it means **there was
      no body to grade in the first place** (e.g. a timeout). That is why the
      quality gate keeps a separate grading-coverage floor (≥ 90%).

    **Accepted among graded cells.** A third, separate ratio: of the cells that were
    graded, the share that was accepted. In the published bundle it is
    `result.coverage`, which carries `basis: graded` and holds
    `accepted / graded` — for experiment 12, **274/277 = 98.917%**. It shares the
    schema label `coverage` with the two metrics above and is **none of them**: its
    denominator is graded cells, not planned cells and not tasks. No gate in this
    repository is set against it.

??? note "Labels you will see alongside these"
    | Label | Meaning |
    | --- | --- |
    | `measured=false` (projection) | Offline calculation over synthetic data. Not measured Azure spend (experiments 01–08). |
    | `measured=true` (measured) | Value measured from real Azure Foundry calls and usage (experiments 09 · 10 · 11 · 12 · 13). |
    | `evidence_tier=directional` | A directional signal, not statistical confidence. Experiments 09 and 10 measured **5 curated tasks**; experiments 11, 12 and 13 measured **24 tasks × 4 arms × 3 repeats = 288 planned cells**. Every measured run is a single tenant and a single measurement, so all of them stay directional. |
    | `cost_complete=true` / `unpriced 0%` | Every cell in the arm was priced at pinned rates. It is a statement about rate coverage, not about invoice reconciliation. |
    | `plan_hash` | Content-addressed hash sealing the workload, policy, and rates. The reference point for reproduction and replay. |

    Check each figure's honesty label (measured/projected) **on its own page** — this
    glossary only unifies the names and definitions; it does not replace the per-page
    claim boundaries. For the boundaries as a whole, see the
    [Honesty Charter](../honesty.md).

## Percentage points (pp)

A difference between two percentages is stated in **percentage points**, abbreviated
**pp** after its first use on a page. 95.8% against 100.0% is a gap of 4.17 pp, not a
4.17% relative change. Pages that use the abbreviation spell it out once before using it.

## Savings figures — always name the comparator

A savings percentage is meaningless without the two arms it divides. Three different
figures appear in this repository, and they are not versions of one another:

| Figure | Experiment | Comparison |
| --- | --- | --- |
| **95.2%** | 12 | `router-cost` against `direct-premium` |
| **95.8%** | 12 | the cheapest cost-complete arm against the highest-cost cost-complete arm (`router-cost` against `router-quality`) |
| **94.7%** | 13 | `router-cost` against `router-quality`, among that run's cost-complete arms |

Quote any of them with its experiment number and its comparator attached.
