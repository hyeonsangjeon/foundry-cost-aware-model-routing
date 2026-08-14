#!/usr/bin/env python3
"""Offline acceptance harness for the fresh-clone onboarding journey (BOLT-03E).

This is the command the completion gate names:

    python scripts/verify_onboarding.py --offline

It runs entirely against the *already-installed* environment and the local
loopback dashboard — zero Azure calls, zero GitHub Star mutations, no network
install. It asserts the onboarding contract without needing a browser engine by
checking, in order:

1. bootstrap detection accepts both declared interpreters (3.11 / 3.12) and
   rejects either end of the range — a below-floor 3.10 and an above-ceiling
   3.13 — with a short message, not a traceback;
2. the served/rendered dashboard ships the success screen + accessible Star CTA
   (HTTPS repo URL, ``rel="noopener noreferrer"``, keyboard-labelled) and no
   auto-loaded external resources;
3. ``cost-router hero --json`` reports a PASS within the post-install budget
   (the machine signal that the offline reproduction reproduced);
4. ``scripts/quickstart.py --ci --no-install`` boots the dashboard headless,
   discovers the bound port, verifies PASS + CTA, emits a machine-readable line,
   and tears the server down cleanly (non-zero on timeout/cleanup failure).

A single ``VERIFY ONBOARDING: PASS`` line and exit 0 mean the contract holds.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from router import onboarding as ob  # noqa: E402
from router.dashboard import DASHBOARD_HTML  # noqa: E402

_QUICKSTART = _REPO_ROOT / "scripts" / "quickstart.py"


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    src = str(_REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


# --- individual checks (return a short detail string; raise AssertionError on fail) ---


def check_bootstrap_detection() -> str:
    choice = ob.detect_supported_python()
    assert choice.version in ob.SUPPORTED_PYTHONS, f"detected {choice.version}, expected 3.11/3.12"

    # Every declared interpreter is accepted as-is when it is the current one —
    # the range has to be provably inclusive, not just provably exclusive.
    for version in ob.SUPPORTED_PYTHONS:
        major, _, minor = version.partition(".")
        accepted = ob.detect_supported_python(
            current_version=(int(major), int(minor)),
            current_executable=f"/usr/bin/python{version}",
            which=lambda _n: None,
        )
        assert accepted.is_current and accepted.version == version, (
            f"{version} is declared supported but was not accepted as the current interpreter"
        )

    # Both ends are rejected, each stating the reason that end fails for: below
    # the floor the router cannot import; above the ceiling it is only untested.
    # Neither may print a traceback at a fresh cloner.
    boundaries = (((3, 10), "datetime.UTC"), ((3, 13), "newer than the tested range"))
    for rejected, expected_reason in boundaries:
        label = f"{rejected[0]}.{rejected[1]}"
        try:
            ob.detect_supported_python(current_version=rejected, which=lambda _n: None)
        except ob.BootstrapError as exc:
            msg = str(exc)
            assert "not supported" in msg, f"{label} rejection should say 'not supported'"
            assert "3.11" in msg and "3.12" in msg, "rejection should name the interpreters"
            assert expected_reason in msg, (
                f"{label} rejection must say why: expected {expected_reason!r} in {msg!r}"
            )
            assert len(msg.splitlines()) <= 4, "rejection message must stay short (no traceback)"
        else:
            raise AssertionError(f"Python {label} should be rejected with a BootstrapError")
    return f"detects {choice.version}; accepts 3.11/3.12; rejects 3.10 and 3.13 with short hints"


def check_success_and_cta_markup() -> str:
    problems = ob.verify_success_markup(DASHBOARD_HTML)
    assert not problems, (
        "success screen / Star CTA contract failed:\n  - " + "\n  - ".join(problems)
    )

    # No auto-loaded external origins; the only external URLs are user CTAs to the
    # canonical repo / docs site (opened on click, never fetched automatically).
    for needle in ('src="http', 'src="//', "//cdn", "@import", "url(http", "<script src"):
        assert needle not in DASHBOARD_HTML, f"external resource load found: {needle}"
    allowed = (
        "https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing",
        "https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing",
    )
    for url in re.findall(r"https?://[^\s\"'<>]+", DASHBOARD_HTML):
        assert url.startswith(allowed), f"unexpected external URL: {url}"
        assert url.startswith("https://"), f"external CTA must be https: {url}"
    return "success panel ships hidden; Star CTA https+noopener+labelled; no external loads"


def check_hero_pass() -> str:
    t0 = time.monotonic()
    res = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "router.cli", "hero", "--json"],
        cwd=str(_REPO_ROOT), env=_child_env(), capture_output=True, text=True, check=False,
    )
    elapsed = time.monotonic() - t0
    assert res.returncode == 0, f"hero --json exited {res.returncode}: {res.stderr[-300:]}"
    payload = json.loads(res.stdout)
    assert ob.hero_json_ok(payload), "hero reproduction did not PASS"
    assert elapsed <= ob.HERO_BUDGET_S, f"hero took {elapsed:.1f}s > {ob.HERO_BUDGET_S:.0f}s gate"
    return f"hero PASS in {elapsed:.2f}s (gate {ob.HERO_BUDGET_S:.0f}s)"


def check_quickstart_ci() -> str:
    t0 = time.monotonic()
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(_QUICKSTART), "--ci", "--no-install"],
        cwd=str(_REPO_ROOT), env=_child_env(), capture_output=True, text=True, check=False,
        timeout=120,
    )
    elapsed = time.monotonic() - t0
    assert res.returncode == 0, (
        f"quickstart --ci exited {res.returncode}:\n{res.stdout[-400:]}\n{res.stderr[-400:]}"
    )
    line = next(
        (ln for ln in res.stdout.splitlines() if ln.startswith("ONBOARDING result=pass")), ""
    )
    assert line, f"no machine-readable PASS line in:\n{res.stdout[-400:]}"
    assert "hero_pass=true" in line and "cta_ok=true" in line, f"CTA/hero not confirmed: {line}"
    assert re.search(r"\bport=\d+\b", line), f"bound port not reported: {line}"

    # cleanup contract: no orphan server should remain after --ci exits.
    ps = subprocess.run(  # noqa: S603
        ["ps", "-eo", "args"], capture_output=True, text=True, check=False,
    )
    orphans = [ln for ln in ps.stdout.splitlines() if "router.cli serve" in ln]
    assert not orphans, f"orphan server survived cleanup: {orphans}"
    return f"headless PASS + machine-readable line + clean teardown in {elapsed:.2f}s"


CHECKS = (
    ("bootstrap detection", check_bootstrap_detection),
    ("success screen + Star CTA", check_success_and_cta_markup),
    ("hero reproduction PASS", check_hero_pass),
    ("quickstart --ci headless", check_quickstart_ci),
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="verify_onboarding.py",
        description="Offline acceptance harness for the fresh-clone journey (BOLT-03E).",
    )
    p.add_argument("--offline", action="store_true",
                   help="assert the offline contract (0 Azure, no reinstall) — the supported mode")
    args = p.parse_args(argv)
    mode = "offline" if args.offline else "offline (default)"
    print(f"verify_onboarding [{mode}] — 0 Azure, 0 Star mutation\n")

    failed = 0
    for name, fn in CHECKS:
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 — report every check, then summarise
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        else:
            print(f"  ✓ {name} — {detail}")

    print("")
    if failed:
        print(f"VERIFY ONBOARDING: FAIL ({failed}/{len(CHECKS)} checks failed)")
        return 1
    print(f"VERIFY ONBOARDING: PASS ({len(CHECKS)}/{len(CHECKS)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
