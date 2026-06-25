#!/usr/bin/env bash
# Local validation gate for cost-aware model routing.
# Grows per build phase — see docs/20-agent-build-harness.md.
# Phase 0: shell syntax · python compile · no-secret scan · .env.sample check.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
say() { printf '\n== %s ==\n' "$1"; }
ok()  { printf '  ok   %s\n' "$1"; }
err() { printf '  ERR  %s\n' "$1"; fail=1; }

# Tracked + untracked-not-ignored files (works before and after commit).
ls_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files --cached --others --exclude-standard "$@"
  else
    find . -path ./.git -prune -o -type f -print
  fi
}

say "shell syntax"
sh_list=$(ls_files '*.sh')
[ -n "$sh_list" ] || echo "  (no shell scripts)"
while IFS= read -r s; do
  [ -n "$s" ] || continue
  if bash -n "$s"; then ok "$s"; else err "$s"; fi
done <<EOF
$sh_list
EOF

say "python compile"
py_list=$(ls_files '*.py')
if [ -z "$py_list" ]; then
  echo "  (no python files yet)"
else
  if printf '%s\n' "$py_list" | tr '\n' '\0' | xargs -0 python3 -m py_compile; then
    ok "compiled python sources"
  else
    err "py_compile failed"
  fi
fi

say "no-secret scan"
# Tier-1 discipline: no real keys, tokens, connection strings, private keys,
# or live Azure endpoints in the tree.
secret_re='(gh[opsu]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]{10,}|AccountKey=[A-Za-z0-9+/=]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|[A-Za-z0-9-]+\.(openai\.azure\.com|azure-api\.net|vault\.azure\.net))'
scan=$(ls_files \
  | grep -vE '^(scripts/validate-local\.sh|\.github/workflows/ci\.yml)$' \
  | grep -vE '\.(svg|png|jpe?g|gif|mp4|ico|pdf|woff2?)$' || true)
if [ -n "$scan" ]; then
  hits=$(printf '%s\n' "$scan" | tr '\n' '\0' | xargs -0 grep -nEI "$secret_re" 2>/dev/null || true)
  if [ -n "$hits" ]; then printf '%s\n' "$hits"; err "potential secret or live endpoint found"; else ok "no secrets or live endpoints detected"; fi
else
  ok "nothing to scan"
fi

say ".env.sample placeholders"
if [ -f .env.sample ]; then
  bad=$(grep -nE '=[[:space:]]*[^[:space:]#]' .env.sample || true)
  if [ -n "$bad" ]; then printf '%s\n' "$bad"; err ".env.sample must hold placeholder NAMES only (empty values)"; else ok ".env.sample has no real values"; fi
else
  echo "  (.env.sample not present yet)"
fi

# Optional toolchain checks — run only when available (later phases / CI).
if [ -d tests ] && python3 -c 'import pytest' >/dev/null 2>&1; then
  say "pytest"
  if python3 -m pytest -q; then ok "tests passed"; else err "tests failed"; fi
fi
if command -v ruff >/dev/null 2>&1; then
  say "ruff"
  if ruff check . ; then ok "lint clean"; else err "ruff reported issues"; fi
fi

say "result"
if [ "$fail" -ne 0 ]; then echo "FAILED"; exit 1; fi
echo "PASSED"
