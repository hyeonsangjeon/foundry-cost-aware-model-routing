"""Shared, dependency-free core for the fresh-clone onboarding journey (BOLT-03E).

Everything here is pure standard library so it can run *before* the editable
install completes (``scripts/quickstart.py`` imports it on a bare interpreter)
and so the offline acceptance harness can exercise the contract without a
browser engine.

Two honesty rules from the wider project carry through here:

* The offline reproduction is a deterministic projection over synthetic data
  (``measured=false``); only a fresh live call ever earns ``measured=true``.
* The Star call-to-action is a *link only*. Nothing in this module (or anything
  that imports it) may star the repository, call the Star API, request GitHub
  write scope, or claim that a star happened.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# --- Constants ---------------------------------------------------------------

#: Interpreters the project declares, tests, and times (pyproject requires >=3.11
#: and classifies 3.11 + 3.12). 3.10 fails to import the router (StrEnum /
#: ``datetime.UTC``), so it is explicitly unsupported.
SUPPORTED_PYTHONS: tuple[str, ...] = ("3.11", "3.12")
MIN_PYTHON: tuple[int, int] = (3, 11)

#: The canonical repository URL — the single allowed Star call-to-action target.
REPO_URL = "https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing"

#: Time contract (§2.1). Hard gates for the offline path; the release smoke uses
#: RELEASE_BUDGET_S end to end. clone+install is telemetry, never a gate here.
HERO_BUDGET_S = 30.0  # post-install `cost-router hero --json` exit 0
READY_BUDGET_S = 10.0  # server process start -> first ready response
RESULT_BUDGET_S = 30.0  # ready -> PASS + accessible CTA verified
RELEASE_BUDGET_S = 600.0  # end-to-end git clone -> PASS+CTA (release smoke only)


class OnboardingError(RuntimeError):
    """Base class for onboarding failures with a short, human-facing message."""


class BootstrapError(OnboardingError):
    """Raised when the environment cannot host the project (e.g. Python < 3.11)."""


class ReadinessTimeout(OnboardingError):
    """Raised when the dashboard never becomes ready within its budget."""


class CleanupError(OnboardingError):
    """Raised when a launched server/child process could not be torn down."""


# --- Python interpreter detection -------------------------------------------


@dataclass(frozen=True)
class PythonChoice:
    """A resolved interpreter to bootstrap the venv with."""

    executable: str
    version: str  # "3.11", "3.12", ...
    is_current: bool


def _version_key(version: str) -> tuple[int, int]:
    major, _, minor = version.partition(".")
    return (int(major), int(minor or 0))


def unsupported_python_message(
    version: str,
    *,
    found: str | None = None,
    platform: str | None = None,
) -> str:
    """Return a *short*, OS-appropriate hint for an unsupported interpreter.

    ``version`` is the rejected interpreter (e.g. ``"3.10"``). ``found`` names a
    supported interpreter discovered on PATH, if any. The message stays a couple
    of lines — a fresh cloner should never see a long traceback.
    """

    plat = (platform or sys.platform).lower()
    supported = " / ".join(SUPPORTED_PYTHONS)
    lines = [
        f"Python {version} is not supported — the router needs {supported} "
        "(3.10 lacks datetime.UTC / StrEnum and fails at import/collection).",
    ]
    if found:
        lines.append(f"Found {found}; re-run with it, e.g.  {found} scripts/quickstart.py")
    elif plat.startswith("darwin"):
        lines.append("Install one with:  brew install python@3.12   (then re-run)")
    elif plat.startswith("win"):
        lines.append("Install Python 3.12 from https://python.org/downloads then re-run.")
    else:
        lines.append(
            "Install one with your package manager, e.g.  "
            "sudo apt install python3.12 python3.12-venv   (then re-run)"
        )
    return "\n".join(lines)


def _which_supported(which=shutil.which) -> tuple[str, str] | None:
    """Return ``(executable, version)`` for the newest supported python on PATH."""

    for version in sorted(SUPPORTED_PYTHONS, key=_version_key, reverse=True):
        exe = which(f"python{version}")
        if exe:
            return exe, version
    return None


def detect_supported_python(
    *,
    current_version: tuple[int, int] = sys.version_info[:2],
    current_executable: str = sys.executable,
    which=shutil.which,
    platform: str | None = None,
) -> PythonChoice:
    """Pick a declared interpreter (3.11/3.12) to bootstrap with.

    Prefers the *current* interpreter when it already qualifies; otherwise it
    searches PATH for ``python3.12``/``python3.11``. Raises :class:`BootstrapError`
    with a short message when nothing suitable exists (the common fresh-clone
    failure is a system ``python3`` that is 3.10).
    """

    cur = f"{current_version[0]}.{current_version[1]}"
    if current_version >= MIN_PYTHON and cur in SUPPORTED_PYTHONS:
        return PythonChoice(executable=current_executable, version=cur, is_current=True)

    found = _which_supported(which)
    if found is not None:
        exe, version = found
        return PythonChoice(executable=exe, version=version, is_current=False)

    raise BootstrapError(unsupported_python_message(cur, platform=platform))


# --- Server URL / readiness --------------------------------------------------

_SERVE_URL_RE = re.compile(r"serving on (http://[0-9A-Za-z_.\-]+:\d+)")


def parse_serve_url(text: str) -> str | None:
    """Extract the actually-bound ``http://host:port`` from server stdout.

    The server prints ``cost-router serving on http://127.0.0.1:8000 (offline)``
    and, on a port collision, rebinds to the next free port — so the printed URL
    is authoritative. Never assume 8000.
    """

    match = _SERVE_URL_RE.search(text or "")
    return match.group(1) if match else None


def http_ok(url: str, *, timeout: float = 2.0) -> bool:
    """Return ``True`` when ``url`` answers with a 2xx status (offline only)."""

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (localhost)
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_for_http_ready(
    url: str,
    *,
    timeout: float = READY_BUDGET_S,
    interval: float = 0.1,
    sleep=time.sleep,
    clock=time.monotonic,
) -> float:
    """Poll ``url`` until it answers, returning the elapsed seconds.

    Raises :class:`ReadinessTimeout` (with the elapsed time) if the budget is
    exceeded — the caller maps that to a non-zero exit.
    """

    start = clock()
    while True:
        if http_ok(url):
            return clock() - start
        elapsed = clock() - start
        if elapsed >= timeout:
            raise ReadinessTimeout(
                f"dashboard was not ready within {timeout:.0f}s (waited {elapsed:.1f}s at {url})"
            )
        sleep(interval)


# --- Success screen + Star CTA contract (§2.5) -------------------------------

_ANCHOR_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf'{name}\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
    return m.group(1) if m else None


def _visible_text(anchor: str) -> str:
    inner = re.sub(r"<[^>]+>", "", anchor)
    return re.sub(r"\s+", " ", inner).strip()


def verify_star_cta(html: str) -> list[str]:
    """Return a list of contract problems with the Star CTA (empty == OK).

    Enforces §2.5's *automatable* guarantees only: a call-to-action linking to
    the canonical repo over HTTPS, keyboard-accessible + clearly labelled, with
    ``rel="noopener noreferrer"`` because it opens a new tab. It deliberately
    does **not** (and must not) verify that a star was applied.
    """

    problems: list[str] = []
    star: str | None = None
    for anchor in _ANCHOR_RE.findall(html or ""):
        if (_attr(anchor, "href") or "").rstrip("/") == REPO_URL:
            star = anchor
            break

    if star is None:
        return [f"no Star CTA anchor linking to {REPO_URL}"]

    href = (_attr(star, "href") or "").rstrip("/")
    if not href.startswith("https://"):
        problems.append("Star CTA must use an https:// URL")
    if href != REPO_URL:
        problems.append(f"Star CTA href is {href!r}, expected {REPO_URL}")

    label = _visible_text(star) or (_attr(star, "aria-label") or "")
    if not label:
        problems.append("Star CTA has no visible text or aria-label (not keyboard-labelled)")

    if (_attr(star, "target") or "").lower() == "_blank":
        rel = {r.lower() for r in (_attr(star, "rel") or "").split()}
        if not {"noopener", "noreferrer"} <= rel:
            problems.append('new-tab Star CTA must set rel="noopener noreferrer"')
    return problems


def verify_success_markup(html: str) -> list[str]:
    """Return problems with the offline success screen markup (empty == OK).

    The success panel must ship *hidden* (revealed only after a PASS, never
    before), must carry the ``measured=false`` honesty label, and must expose the
    three call-to-action anchors. It never bakes in a favorable example number.
    """

    problems: list[str] = []
    text = html or ""

    panel = re.search(r"<section\b[^>]*id=\"journeyPanel\"[^>]*>", text, re.IGNORECASE)
    if not panel:
        problems.append('no success panel (id="journeyPanel")')
    elif "hidden" not in panel.group(0):
        problems.append("success panel must ship hidden (revealed only after a PASS)")

    if 'id="journeyVerdict"' not in text:
        problems.append('no PASS verdict element (id="journeyVerdict")')
    if "measured=false" not in text:
        problems.append("success panel must carry the measured=false honesty label")

    for cta_id in ("ctaTrace", "ctaMethod", "ctaStar"):
        if f'id="{cta_id}"' not in text:
            problems.append(f'missing call-to-action anchor id="{cta_id}"')

    problems.extend(verify_star_cta(text))
    return problems


# --- Telemetry ---------------------------------------------------------------


@dataclass
class Telemetry:
    """Timing/segment record for the onboarding run (recorded, not gated).

    ``segments`` holds ungated measurements (clone, venv, pip, install);
    ``gates`` holds the hard-gate durations (hero, readiness, result).
    """

    platform: str
    python: str
    segments: dict[str, float] = field(default_factory=dict)
    gates: dict[str, float] = field(default_factory=dict)

    def record(self, name: str, seconds: float, *, gate: bool = False) -> None:
        (self.gates if gate else self.segments)[name] = round(seconds, 3)

    def as_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "python": self.python,
            "segments_s": dict(self.segments),
            "gates_s": dict(self.gates),
        }


# --- Process helpers ---------------------------------------------------------


def hero_json_ok(payload: dict) -> bool:
    """Return ``True`` when a ``cost-router hero --json`` payload reports a PASS.

    The offline reproduction passes when the top-level ``ok`` is true and every
    contracted check (coverage / savings / tasks) is ok. This is the machine
    signal the harness treats as the reproduction PASS.
    """

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return False
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        return False
    return all(isinstance(c, dict) and c.get("ok") is True for c in checks)


def terminate_process_tree(proc: subprocess.Popen, *, timeout: float = 5.0) -> None:
    """Tear down ``proc`` and its process group; raise :class:`CleanupError` if it survives.

    The server is launched in its own session (``start_new_session=True``) so the
    whole tree can be signalled at once. Any survivor is a cleanup failure the
    ``--ci`` path must surface as a non-zero exit.
    """

    if proc.poll() is not None:
        return

    import os
    import signal

    def _signal(sig: int) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.send_signal(sig)
            except (ProcessLookupError, OSError):
                pass

    _signal(signal.SIGTERM)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _signal(signal.SIGKILL)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise CleanupError(
                f"server process {proc.pid} did not exit after SIGTERM+SIGKILL"
            ) from None
