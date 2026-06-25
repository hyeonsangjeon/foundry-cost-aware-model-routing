# Contributing

Thanks for your interest in this project. Keep contributions small, testable,
and free of private planning material.

## Ground rules

1. Keep local-only notes, private links, launch plans, tenant data, endpoints,
   and secrets out of Git.
2. Use synthetic sample data only.
3. Add or update tests for behavior changes.
4. Run the local validation gate before sharing a branch.

## Development

```bash
make dev      # editable install with dev extras (ruff, pytest)
make check    # local validation gate (must pass before a PR)
make test     # pytest
make lint     # ruff
```

## Before opening a pull request

- `bash scripts/validate-local.sh` passes (shell, python compile, no-secret scan).
- New code has tests; `pytest` is green.
- No secrets, tenant identifiers, or customer data anywhere in the diff.
- Commits are scoped and described.
