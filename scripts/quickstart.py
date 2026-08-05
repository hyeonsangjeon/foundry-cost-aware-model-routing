#!/usr/bin/env python3
"""Fresh-clone quickstart: bootstrap the venv, then prove the offline path (BOLT-03E).

This is the friendliest way from a bare ``git clone`` to a working result. It is
pure standard library so it runs on the interpreter a fresh cloner already has,
*before* anything is installed.

    python3 scripts/quickstart.py            # bootstrap + open the dashboard
    python3 scripts/quickstart.py --ci       # headless: verify PASS + CTA, then exit
    python3 scripts/quickstart.py --foundry  # also install the credentialed extra

What it does (Track A — free, 0 Azure):

1. Detect a declared interpreter (CPython 3.11 / 3.12) *before* creating a venv.
2. Create ``.venv``, upgrade pip inside it, editable-install the project.
3. Run ``cost-router hero --json`` and confirm the offline reproduction PASSes
   (hard gate: within 30 s of install).
4. Boot the dashboard, discover the *actual* bound port (never assume 8000),
   wait for readiness (<=10 s), and confirm the served success screen carries an
   accessible Star call-to-action (<=30 s).

Honesty rules it keeps: the offline reproduction is ``measured=false`` (a fresh
live call is the only thing ever labelled measured); the Star CTA is a link only
— this script never stars the repo, calls the Star API, or asks for write scope.

``--foundry`` installs the credentialed extra and prints the Track B next steps
(``.foundry.local.yaml`` -> ``doctor`` -> ``benchmark smoke``); it does not make
any Azure call itself.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from router import onboarding as ob  # noqa: E402


def _log(msg: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(msg, flush=True)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False,
        env=_child_env(),
    )


def _child_env() -> dict[str, str]:
    """Child env with the repo ``src`` on PYTHONPATH.

    Works whether or not the package is pip-installed: the editable install in a
    freshly bootstrapped venv already exposes ``router``; prepending ``src`` also
    covers the ``--no-install`` harness path where the checkout is run in place.
    """

    env = dict(os.environ)
    src = str(_REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


def _short_fail(stage: str, detail: str) -> None:
    """Print a short, OS-appropriate failure note — never a raw traceback."""

    print(f"\nquickstart: {stage} failed.\n{detail}".rstrip(), file=sys.stderr, flush=True)


# --- bootstrap ---------------------------------------------------------------


def bootstrap(venv_dir: Path, *, foundry: bool, tele: ob.Telemetry) -> Path:
    """Create the venv and editable-install the project; return the venv python.

    Raises :class:`ob.BootstrapError` with a short message on any failure.
    """

    choice = ob.detect_supported_python()
    _log(f"→ using CPython {choice.version} ({choice.executable})")

    t0 = time.monotonic()
    res = _run([choice.executable, "-m", "venv", str(venv_dir)])
    if res.returncode != 0:
        raise ob.BootstrapError(
            "Could not create a virtual environment.\n"
            + _venv_hint()
            + _tail(res.stderr)
        )
    tele.record("venv", time.monotonic() - t0)

    py = _venv_python(venv_dir)
    t0 = time.monotonic()
    res = _run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    if res.returncode != 0:
        raise ob.BootstrapError("Could not upgrade pip inside the venv." + _tail(res.stderr))
    tele.record("pip_upgrade", time.monotonic() - t0)

    target = ".[foundry]" if foundry else "."
    _log(f"→ installing {target} (editable) — one-time")
    t0 = time.monotonic()
    res = _run([str(py), "-m", "pip", "install", "-e", target], cwd=_REPO_ROOT)
    if res.returncode != 0:
        raise ob.BootstrapError(
            f"Editable install of {target} failed." + _tail(res.stderr)
        )
    tele.record("install", time.monotonic() - t0)
    return py


def _venv_hint() -> str:
    plat = sys.platform.lower()
    if plat.startswith("linux"):
        return "On Debian/Ubuntu the venv module may need:  sudo apt install python3-venv\n"
    return ""


def _tail(text: str, *, lines: int = 6) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return "\n" + "\n".join(text.splitlines()[-lines:])


# --- hero PASS proof ---------------------------------------------------------


def run_hero(py: Path, *, tele: ob.Telemetry) -> dict:
    """Run ``cost-router hero --json`` and return the payload; enforce the 30 s gate."""

    t0 = time.monotonic()
    res = _run([str(py), "-m", "router.cli", "hero", "--json"], cwd=_REPO_ROOT)
    elapsed = time.monotonic() - t0
    tele.record("hero", elapsed, gate=True)
    if res.returncode != 0:
        raise ob.OnboardingError("`cost-router hero --json` exited non-zero." + _tail(res.stderr))
    try:
        payload = json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        raise ob.OnboardingError(f"hero --json did not emit JSON: {exc}") from None
    if not ob.hero_json_ok(payload):
        raise ob.OnboardingError("hero reproduction did not PASS (ok/checks not all true).")
    if elapsed > ob.HERO_BUDGET_S:
        raise ob.OnboardingError(
            f"hero took {elapsed:.1f}s, over the {ob.HERO_BUDGET_S:.0f}s post-install gate."
        )
    return payload


def _tasks_from_hero(payload: dict) -> int | None:
    for check in payload.get("checks", []):
        if isinstance(check, dict) and check.get("name") == "tasks":
            digits = "".join(ch for ch in str(check.get("detail", "")) if ch.isdigit() or ch == " ")
            head = digits.strip().split(" ", 1)[0]
            if head.isdigit():
                return int(head)
    return None


# --- dashboard boot + readiness ---------------------------------------------


def boot_dashboard(
    py: Path, host: str, port: int, *, tele: ob.Telemetry
) -> tuple[subprocess.Popen, str]:
    """Start the offline dashboard in its own session; return (process, base_url).

    The bound URL is read from the server's stdout (it rebinds on a busy port and
    prints where it actually landed), so the caller never assumes port 8000.
    """

    proc = subprocess.Popen(  # noqa: S603
        [str(py), "-m", "router.cli", "serve", "--host", host, "--port", str(port)],
        cwd=str(_REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=_child_env(),
    )

    lines: list[str] = []
    url_box: list[str] = []

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            found = ob.parse_serve_url(line)
            if found and not url_box:
                url_box.append(found)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    t0 = time.monotonic()
    while not url_box:
        if proc.poll() is not None:
            raise ob.OnboardingError(
                "dashboard process exited before binding." + _tail("".join(lines))
            )
        if time.monotonic() - t0 > ob.READY_BUDGET_S:
            raise ob.ReadinessTimeout("dashboard never printed a bound URL within the budget.")
        time.sleep(0.05)

    base_url = url_box[0]
    ob.wait_for_http_ready(base_url + "/healthz", timeout=ob.READY_BUDGET_S)
    tele.record("readiness", time.monotonic() - t0, gate=True)
    return proc, base_url


def verify_result(base_url: str, *, tele: ob.Telemetry) -> None:
    """Fetch the served dashboard and confirm the success screen + Star CTA contract."""

    t0 = time.monotonic()
    with urllib.request.urlopen(base_url + "/", timeout=5) as resp:  # noqa: S310 (localhost)
        html = resp.read().decode("utf-8", "replace")
    problems = ob.verify_success_markup(html)
    if problems:
        raise ob.OnboardingError("served success screen failed its contract:\n  - " +
                                 "\n  - ".join(problems))
    elapsed = time.monotonic() - t0
    tele.record("result", elapsed, gate=True)
    if elapsed > ob.RESULT_BUDGET_S:
        raise ob.OnboardingError(
            f"result verification took {elapsed:.1f}s, over the {ob.RESULT_BUDGET_S:.0f}s gate."
        )


# --- success rendering (from the sealed snapshot) ----------------------------


def print_success(payload: dict, base_url: str) -> None:
    tasks = _tasks_from_hero(payload)
    count = "—" if tasks is None else str(tasks)
    print("")
    print("  ✓ Reproduction passed")
    print(f"    {count} tasks · replay verified · measured=false")
    print("    → Inspect a routing trace   → View methodology")
    print(f"    → ★ Useful? Star it on GitHub — {ob.REPO_URL}")
    print("    (a link only — nothing here stars the repo for you)")
    print(f"    dashboard: {base_url}/?run=1")
    print("")


def print_track_b() -> None:
    print("")
    print("Track B (credentialed) — target / in progress, needs your Foundry:")
    print("  1. cp .foundry.local.example.yaml .foundry.local.yaml   # fill in your deployments")
    print("  2. cost-router doctor            # read-only pre-flight (Entra via az login)")
    print("  3. cost-router benchmark smoke   # one paid wiring call → measured=true")
    print("  (this script made 0 Azure calls; run the above yourself when ready)")


# --- orchestration -----------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    tele = ob.Telemetry(platform=platform.platform(), python=platform.python_version())

    # 1. interpreter + install
    try:
        if args.no_install:
            if sys.version_info[:2] < ob.MIN_PYTHON:
                cur = f"{sys.version_info[0]}.{sys.version_info[1]}"
                _short_fail("environment", ob.unsupported_python_message(cur))
                return 3
            py = Path(sys.executable)
        else:
            py = bootstrap(Path(args.venv), foundry=args.foundry, tele=tele)
    except ob.BootstrapError as exc:
        _short_fail("bootstrap", str(exc))
        return 3

    # 2. hero PASS proof (hard gate)
    try:
        payload = run_hero(py, tele=tele)
    except ob.OnboardingError as exc:
        _short_fail("reproduction", str(exc))
        return 4

    # 3. dashboard boot + result verification
    proc: subprocess.Popen | None = None
    try:
        proc, base_url = boot_dashboard(py, args.host, args.port, tele=tele)
        verify_result(base_url, tele=tele)
    except ob.OnboardingError as exc:
        _short_fail("dashboard", str(exc))
        _safe_teardown(proc)
        return 4

    # 4. mode-specific finish
    if args.json:
        print(json.dumps({"result": "pass", "ready_url": base_url,
                          "telemetry": tele.as_dict()}, ensure_ascii=False))

    if args.ci:
        port = int(base_url.rsplit(":", 1)[1])
        print(
            f"ONBOARDING result=pass ready_url={base_url} port={port} "
            f"hero_pass=true cta_ok=true "
            f"hero_s={tele.gates.get('hero', 0):.2f} ready_s={tele.gates.get('readiness', 0):.2f} "
            f"result_s={tele.gates.get('result', 0):.2f}",
            flush=True,
        )
        try:
            ob.terminate_process_tree(proc)
        except ob.CleanupError as exc:
            _short_fail("cleanup", str(exc))
            return 5
        return 0

    # interactive: show the honest success screen, open the browser, keep serving
    print_success(payload, base_url)
    if args.foundry:
        print_track_b()
    if args.open:
        opened = False
        try:
            opened = webbrowser.open(base_url + "/?run=1")
        except Exception:  # noqa: BLE001 — a headless box must not crash the journey
            opened = False
        if not opened:
            print(f"open this in your browser:  {base_url}/?run=1", flush=True)
    print("serving the offline dashboard — press Ctrl-C to stop.", flush=True)
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        _safe_teardown(proc)
    return 0


def _safe_teardown(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        ob.terminate_process_tree(proc)
    except ob.CleanupError as exc:
        _short_fail("cleanup", str(exc))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="quickstart.py",
        description="Fresh-clone bootstrap + offline reproduction check (BOLT-03E).",
    )
    p.add_argument("--ci", action="store_true",
                   help="headless: verify PASS + CTA, print a machine-readable line, then exit")
    p.add_argument("--foundry", action="store_true",
                   help="also install the credentialed extra and print Track B next steps")
    p.add_argument("--no-install", action="store_true",
                   help="skip venv/install; use the current interpreter (for tests/CI harness)")
    p.add_argument("--venv", default=str(_REPO_ROOT / ".venv"),
                   help="venv directory (default .venv)")
    p.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=None,
                   help="bind port; default 0 (ephemeral) in --ci, else 8000")
    p.add_argument("--no-open", dest="open", action="store_false",
                   help="do not open a browser (interactive mode)")
    p.add_argument("--json", action="store_true", help="also emit a JSON summary with telemetry")
    args = p.parse_args(argv)
    if args.port is None:
        args.port = 0 if args.ci else 8000
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
