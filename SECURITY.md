# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Instead, use
GitHub's private vulnerability reporting:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability** to open a private advisory.

We will acknowledge the report and work with you on a fix and disclosure
timeline.

## Secret-handling discipline

This project is built to keep secrets out of the tree by default:

- Real endpoints, tenant/subscription ids, deployment names, keys, and raw
  live responses are **never committed** — they are `.gitignore`d and a
  no-secret scan runs in `scripts/validate-local.sh` and in CI.
- Only synthetic samples (`*.sample.*`) and placeholder templates
  (`*.example.*`, `.env.sample`) are committed.
- In `apim-gateway`/`full` deployments the gateway holds model credentials; the
  router and demo app never receive raw model keys.

If you find a committed secret, treat it as compromised: rotate it immediately
and report it via the private advisory flow above.
