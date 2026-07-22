# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added
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
