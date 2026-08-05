# Original Coding Benchmark

A small suite of **24 original coding tasks** with fully automated, offline
graders. Every task is authored from scratch (no verbatim public problems) and
ships with a grader plus two fixtures that prove the grader actually
discriminates correct from incorrect solutions.

- **Source:** original (see contamination notes below)
- **License:** MIT (whole suite)
- **Execution:** Python 3.12 standard library only, network blocked, per-task
  subprocess, fixed timeout, pinned `PYTHONHASHSEED` / locale / timezone / seed.

## Difficulty and type mix

| Difficulty | Count |
| ---------- | ----- |
| easy       | 8     |
| medium     | 10    |
| hard       | 6     |

Types: implementation (6), edge-case (5), bug-fix (5), refactor (4),
test-writing (4).

> Difficulty is a **design label, not a measurement.** Real pass rates come later
> from a paid benchmark run; nothing here was calibrated against a model.

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

Explicitly out of scope as grading signals: LLM judges, natural-language quality
scoring, wall-clock performance, and any external network use.

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

`verify.py` is the most important gate: a grader that passes everything (or fails
everything) is worthless, so it fails loudly if any task's `reference.py` does
not PASS and `wrong.py` does not FAIL. It also runs inside the repo's `pytest`
suite (`tests/test_benchmark_original_coding.py`) to guard against drift.

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
