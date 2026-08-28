# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added
- **Multi-provider fleet routing** (`provider` field): a fleet catalog entry can
  now declare `provider: openai` (default — Azure OpenAI chat-completions) or
  `provider: foundry` (Azure AI Model Inference, `*.services.ai.azure.com/models`)
  so partner/OSS deployments (DeepSeek, Mistral, xAI, Moonshot, Meta/Llama,
  Cohere, MS/Phi) and Azure OpenAI models on the **same** Foundry resource each
  call through the correct surface, under one keyless Entra identity. The live
  client resolves the inference endpoint from the resource name (override with
  `AZURE_AI_FOUNDRY_INFERENCE_ENDPOINT`). `cost-router models list` gains a
  **surface** column and the `/fleet` payload + dashboard now report it. New
  bundled full-bench samples: `samples/fleet/foundry-ext-full.fleet.yaml` and
  `samples/pricing/foundry-ext-full.yaml` (11 chat deployments across 8
  providers). Requires the `foundry` extra's new `azure-ai-inference` dep.
- **Fleet registry** (`router.fleet`): register your deployed models and pick
  which plays each arm (router/cheapest/premium/ensemble) from a YAML config
  (`FOUNDRY_FLEET_PATH` / `--fleet`), the terminal (`cost-router models
  list|show|select`, incl. an interactive `/model` picker), or the dashboard's
  "Fleet & live routing" panel. `foundry arena` now builds its slate from the
  registry. Bundled samples: `samples/fleet/foundry-5series.fleet.yaml` and a
  single-deployment example. Selections persist to a gitignored
  `.foundry-fleet.local.yaml`.
- **Onboarding rewrite** (`README.md`): value-forward intro, a prominent
  **Requirements** block (Python 3.11+), clone/venv/install Quickstart, and a
  two-track path — *offline preview* (`hero`) vs. *make it real* (register a
  fleet → `foundry arena --live` → `measured=true`).
- `cost-router serve` / `hero --serve` now fall back to the next free port when
  the requested one is busy (no more `Address already in use` traceback) and
  print the actual URL.
- Initial package scaffold, validation script, CI workflow, policy schema,
  placeholder policy data, synthetic sample data, and tests.
- Hardened `.gitignore` for secrets, local-only planning material, tenant data,
  live responses, and deploy artifacts.
- Router core for rule-based classification, deterministic candidate selection,
  trace construction, and offline signal fixtures.
- Local budget gate, replay scripts, and eval summary for sample fixtures.

### Changed
- **Plain-language inner docs pages, and a gate against the jargon returning.**
  The bilingual manual, lab-notebook and honesty pages (`docs/en`, `docs/ko`)
  dropped the repo's coined vocabulary for plain wording, matching the home-page
  pass: the measured/measurement bridge → the live measurement adapter (ko 실측
  어댑터), wiring/배선 → measurement path/integration (측정 경로·측정 반영),
  spotlight/스포트라이트 → the representative task (대표 태스크), coverage cliff →
  the pass-rate cliff (통과율 절벽), the fan-out dial → the fan-out threshold
  (팬아웃 임계값), reproducibility contract → the reproducibility criteria (재현성
  통과 기준), authority label → claim-source label (주장 근거 라벨), arena prose →
  the four-way comparison (네 방식 비교), centerpiece → Primary comparison (핵심
  비교), slate → the candidate set / role assignment (후보 모델 세트·역할 배정),
  and the "5-minute wow" phrasing was deleted. First-use plain glosses were added the first time a term appears in
  a page (arm, preregistration, fan-out, fail-closed, provenance, post-hoc, and
  the PTU/PAYG/APIM full forms), and the three names kept for continuity —
  **Fleet**, the **audit ledger**, the **Experiment Atlas** — each gained a
  self-contained one-line description. Retained deliberately: the CLI `arena`
  command, config keys (`slate`, `compare_min_value`, `spotlight`), fixture and
  path tokens, HTML anchors, and the dashboard `"both-win"` label. Page titles
  and the "Related documents" footer nav are a later wave, so `foundry-live.md`
  and `head-to-head.md` keep their retired H1s for now. `scripts/check_terminology.py`
  gains **Rule F**, which fails the build if any retired inner-page coinage
  returns to prose — with code spans, anchors, UI labels, H1 titles, cross-line
  code, and the footer nav masked, and the Korean `lab-notebook/devlog.md`
  excluded as a dated journal. Two structural guards ship alongside: a cross-page
  anchor check in `scripts/check_i18n_site.py` (so a renamed heading cannot orphan
  an inbound `page#fragment` link) and a test that re-renders the committed
  Korean 03d dashboard SVGs and byte-compares them.
  The reader's first screen in each language — `README.md`, `docs/en/index.md`,
  `docs/ko/index.md` — dropped repo-coined jargon for plain product wording:
  cockpit → the (local) browser run screen, wiring proof → an end-to-end
  call-path check, flagship/hero prose → the default cost-and-coverage
  experiment (and experiment 01's public name → *Try-cheap-first routing* /
  저렴한 모델 우선 라우팅), while the *ensemble tax*, *cost governor* and *human
  gate* coinages were deleted outright. The one-measurement caveat now reads as
  two plain sentences (a directional signal; the run passed its pre-registered
  reporting criteria) instead of "directional (publishable)". CLI identifiers
  (`cost-router hero`), path tokens (`results/cockpit/<run-id>`), product names
  (Model Router) and the "complementary, not a replacement" frame are unchanged.
  `scripts/check_terminology.py` gains **Rule E**, which fails the build if any
  retired coinage returns to those three surfaces, with code spans and fenced
  CLI comments masked so an identifier is never read as prose; a tree-wide sweep
  is deferred because the same words still stand on later-wave surfaces.
- **Korean docs terminology, and a gate against it drifting back.** Six English
  fragments in `docs/ko` prose were restored to the wording the docs already
  used on other pages — 아암 → 비교 전략, prereg → 사전등록, pinned 요율 → 고정
  요율, exec-signals → 실행 신호, void 런 → 무효 처리된 실행, scope-out → 범위
  제외 — 32 occurrences over 31 lines in 8 pages. Names were deliberately left
  alone: preregistration filenames, schema keys, code spans, link targets and
  the uppercase `VOID` status value account for 15 kept occurrences over 10
  lines. `scripts/check_terminology.py` gains **Rule D**, which fails the build
  if any of the six returns to Korean prose, with `lab-notebook/devlog.md`
  excluded as a dated journal that is not edited retroactively.
