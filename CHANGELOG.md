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
