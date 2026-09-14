# Original Coding Benchmark

A small suite of **24 original coding tasks** with fully automated, offline
graders. Every task is authored from scratch (no verbatim public problems) and
ships with a grader plus two fixtures that prove the grader actually
discriminates correct from incorrect solutions.

- **Source:** original (see contamination notes below)
- **License:** MIT (whole suite)
- **Execution:** Python 3.12 standard library only, network blocked, per-task
  subprocess, fixed timeout, pinned `PYTHONHASHSEED` / locale / timezone / seed.

## Where this suite is used

This suite is the workload the repository calls **`curated-24`**, and
`tasks.jsonl` is the file every paid run of the router-mode comparison was
pointed at. Three such runs exist, each bound to its own preregistration:

| Run | Preregistration | Published priced-cell total / cap | Outcome |
| --- | --- | --- | --- |
| **Experiment 11** (artifacts: `03D`) | [`prereg-03d-router-modes.md`](prereg-03d-router-modes.md) | $3.467533 / $20.00 — **excludes withheld cells** | **VOID** — [write-up](../../docs/en/lab-notebook/11-router-modes-void.md) |
| **Experiment 12** (artifacts: `03D-2`) | [`prereg-03d2-router-modes.md`](prereg-03d2-router-modes.md) | $3.269553 / $20.00 — every arm cost-complete | publishable — [write-up](../../docs/en/lab-notebook/12-router-modes-measured.md) |
| **Experiment 13** (artifacts: `03D-3`) | [`prereg-03d3-router-modes.md`](prereg-03d3-router-modes.md) | $4.196595 / $20.00 — **excludes withheld cells** | publishable, one arm claim-blocked — [write-up](../../docs/en/lab-notebook/13-router-modes-rate-card-gap.md) |

**Read that column as priced cells only, not as a bill.** Each figure is the sum
of the cells this repository could price from token usage × a pinned rate card. A
cell whose backend had no row in the card is withheld rather than guessed
(`cost_usd = null`, never `0.0`), so it contributes nothing to the total. Two of
the three runs contain such cells: experiment 11 withheld **43.4% of its cells**
(125 of 288, all routed to `grok-4-1-fast-reasoning`), and experiment 13 withheld
**12 of the 72 cells in its `router-balanced` arm** (16.7%, routed to
`gpt-5.6-terra`). For those runs the real charge is higher than the figure shown,
by an amount this repository does not claim to know. **None of these totals is an
Azure invoice total**, and the `$20.00` column is the run's own budget cap, not a
billed amount.

Each run sealed the same workload fingerprint,
`sha256:391d2f705e8b52c3826d20d80ef2c37b3c1e8a6eb69e8bd41bb2685ce46c0656`, so a
later change to any prompt is detectable as a different experiment rather than a
different result for the same one.

**24 tasks is below the threshold for a statistically reliable result.**
Microsoft's Model Router evaluation guide advises 100 or more workload prompts
for that, and says fewer than 30 give only a directional signal, so every
measured result on this suite carries `evidence_tier = directional`
([measurement protocol §3.4](../../docs/en/manual/measurement-protocol.md)).

## Terms these runs use

The preregistrations and the measured write-ups use six terms in a narrow
sense. They are defined here because the preregistrations are byte-frozen and
cannot define them in place.

| Term | Meaning |
| ---- | ------- |
| **arm** | One comparison strategy evaluated against the same workload under the same measurement plan. The router-mode runs use four: `router-cost`, `router-balanced`, `router-quality`, `direct-premium`. |
| **cell** | One (task × arm × repeat) attempt — the unit a run dispatches and grades. 24 tasks × 4 arms × 3 repeats = **288 planned cells** per run. |
| **pass rate** | Tasks that passed ÷ tasks attempted. Denominator: 24 tasks per arm. |
| **grading coverage** | Cells that produced an answer to grade ÷ cells planned. Denominator: 72 cells per arm. A timeout removes a cell from grading, so the two metrics diverge; see the [glossary](../../docs/en/manual/glossary.md). |
| **cost-complete** | Every cell in the arm had a pinned rate. One cell without a rate makes the arm `cost_complete = false`; its cost is withheld (`cost_usd = null`, never `0.0`), and the arm reports but carries no savings claim. |
| **pp** | Percentage points — the arithmetic difference between two percentages. A drop from 100% to 95.8% is 4.17 pp, not 4.17%. |

The preregistrations also cite section numbers — `BOLT-03 §8`, `§9`, `§10`,
`03B`, `03C`, `03Z-b` — from an internal working plan that is not published.
Where a number matters to reading the document, the rule it names is written out
beside it: `§8` is the four-step hash order each preregistration reproduces under
"§8 hash order", `§10` is the rule that effective-parameter divergence marks a
comparison `confounded=true`, and `03Z-b` is the fail-closed handling of unpriced
cells that each preregistration states in full. Treat the numbers as filing
labels, not as references you are expected to resolve.

## Difficulty and type mix

| Difficulty | Count |
| ---------- | ----- |
| easy       | 8     |
| medium     | 10    |
| hard       | 6     |

Types: implementation (6), edge-case (5), bug-fix (5), refactor (4),
test-writing (4).

> Difficulty is a **design label, not a measurement.** The three paid runs above
> did measure pass rates on this suite, but none of them calibrated these labels:
> no label was assigned or revised from a model's result. Read the mix as the
> spread the tasks were written to, not as observed difficulty.

## Layout

```
benchmarks/original-coding/
  tasks.jsonl          # one task per line (the published task set)
  harness/             # offline grading infrastructure
    sandbox.py         # determinism + network block (activated in the child)
    checks.py          # reusable grading primitives
    runner.py          # subprocess entry: grade one submission for one task
    grade.py           # driver: run a grader in an isolated subprocess
    verify.py          # bidirectional verification over fixtures/
    spec_hash.py       # recompute/verify each task's spec_hash
  graders/<task_id>.py # per-task grader exposing grade(module, source)
  fixtures/<task_id>/
    reference.py       # a correct solution — MUST pass the grader
    wrong.py           # a deliberately incorrect solution — MUST fail
```

Graders and reference/mutant sources live **outside** `tasks.jsonl`; the task
file never contains answer code or hidden tests.

## Submission contract

A model is given a task's `system_prompt` + `user_prompt` and must return **one
self-contained, standard-library-only Python module**:

- **implementation / edge-case** — define the requested function.
- **bug-fix** — return the corrected function (same name/signature).
- **refactor** — return the restructured function (same name/signature),
  behavior preserved, satisfying the stated structural requirement.
- **test-writing** — define a module-level list `TESTS`; each element is a
  function `test(impl)` that asserts a property of `impl.<target>` and raises
  `AssertionError` on failure. The target function is **not** defined by the
  submission.

## Grading disciplines

- **implementation / edge-case** — hidden input/output cases plus exact
  exception-type checks.
- **bug-fix** — a bug-reproduction test (fails on the shipped defect) *and* a
  regression suite, both of which must pass on the fix.
- **refactor** — behavior-preservation tests *and* AST structural constraints
  (e.g. bounded nesting depth, a required comprehension, a single loop).
- **test-writing** — the submitted `TESTS` must pass a correct reference
  implementation and **kill** a fixed set of mutants (each mutant must be failed
  by at least one test).

Explicitly out of scope **as grading signals**: LLM judges, natural-language
quality scoring, wall-clock performance, and any external network use. A paid run
still records per-cell latency as a diagnostic — that is how the 90-second read
timeout in experiment 12 was found — but no latency figure ever decides whether a
submission passed.

## What validates the grader

A grader that passes everything, or fails everything, would produce a clean-looking
run that measures nothing. So every task ships two fixtures and the suite checks
the grader against both before any model is called:

- `fixtures/<task_id>/reference.py` — a correct solution, which **must PASS**;
- `fixtures/<task_id>/wrong.py` — a deliberately incorrect solution, which **must FAIL**.

`harness/verify.py` runs both directions across all 24 tasks and fails loudly if
either expectation breaks, and `tests/test_benchmark_original_coding.py` runs it
inside the repository's `pytest` suite so the check cannot rot unnoticed.

This is what the preregistrations mean by `grader: {kind: exec-signals, version: 1}`.
The grader is deterministic code reading execution signals, and the fixtures above
are its validation; no model judges another model's output anywhere in this suite.

## Running the grader

All commands are offline. From this directory:

```bash
# Grade one candidate submission for one task:
python harness/grade.py --task braid-channels --submission path/to/output.py

# Grade a directory of <task_id>.py submissions against every task:
python harness/grade.py --all --submissions-dir path/to/outputs/

# Prove every grader discriminates (reference passes, wrong fails) — 24 tasks:
python harness/verify.py

# Verify the spec_hash of every task in tasks.jsonl:
python harness/spec_hash.py
```

`verify.py` is the gate described under
[What validates the grader](#what-validates-the-grader) above — every task's
`reference.py` must PASS and its `wrong.py` must FAIL. Run it after editing any
grader or fixture, and treat a failure there as blocking.

## `tasks.jsonl` schema

Each line is a JSON object:

| field | meaning |
| ----- | ------- |
| `id` | task identifier (matches `graders/<id>.py` and `fixtures/<id>/`) |
| `difficulty` | `easy` / `medium` / `hard` (design intent) |
| `type` | `implementation` / `edge-case` / `bug-fix` / `refactor` / `test-writing` |
| `system_prompt`, `user_prompt` | the exact prompts shown to the model |
| `pass_criteria` | human-readable description of what the grader checks |
| `source` | always `original` |
| `license` | always `MIT` |
| `contamination_risk` | always `low` |
| `expected_output_tokens` | design estimate, not a limit |
| `spec_hash` | sha256 over the normative fields (type, difficulty, prompts, pass_criteria) |
| `created_at` | authoring date |

`spec_hash` pins what the model is asked to do, so any later change to a task's
normative content is detectable while bookkeeping fields stay free to change.

## Contamination avoidance

Tasks were written to reduce train/test overlap:

- canonical interview/kata problems (two-sum, valid-parentheses, LRU cache, and
  the like) are avoided;
- unfamiliar domain framing and freshly named APIs are used;
- a mere numeric/variable rename of an existing problem does **not** count as
  original;
- no answer code or hidden tests appear in `tasks.jsonl`;
- graders live in a separate directory from the task prompts.

## Methodology references

We borrowed **methodology, not content** — no problem text or solutions were
copied from any of these:

- Chen et al., *Evaluating Large Language Models Trained on Code* (HumanEval,
  2021) — functional correctness via hidden unit tests.
- Austin et al., *Program Synthesis with Large Language Models* (MBPP, 2021) —
  short Python tasks graded by execution.
- Jimenez et al., *SWE-bench* (2023) — fail-to-pass + pass-to-pass test framing,
  mirrored by our bug-fix reproduction + regression design.
- DeMillo, Lipton & Sayward, *Hints on Test Data Selection* (1978), and modern
  mutation-testing tools (e.g. `mutmut`, `cosmic-ray`) — the basis of the
  test-writing grader.
- Data-contamination analyses of code/LLM benchmarks (e.g. Sainz et al., 2023) —
  the motivation for authoring original tasks and tracking `contamination_risk`.

## Future work

- **public-calibration set** — a small, separately labeled slice drawn from
  permissively licensed public problems, to anchor difficulty against external
  baselines (planned; not included in this suite).

Until that slice exists, a result on this suite supports a decision about
**routing** — which arm costs less per passed task on these 24 tasks — and not a
decision about how hard the tasks are relative to any published benchmark.
