"""Regression tests for the fresh-clone onboarding journey (BOLT-03E).

Covers three surfaces, offline and deterministic:

* :mod:`router.onboarding` — the reusable core (python detection + short hints,
  server-URL parsing, readiness polling, the success-screen + Star CTA contract,
  and process-tree teardown);
* ``scripts/quickstart.py`` — the bootstrap/launch tool, exercised headless via
  ``--ci --no-install`` (real subprocess) and via an in-process readiness-timeout
  that must map to a non-zero exit with a clean teardown;
* ``scripts/verify_onboarding.py`` — the offline acceptance harness the gate runs.

No test here touches Azure or GitHub; the Star CTA is only ever asserted to be a
correctly-formed *link*.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

from router import onboarding as ob
from router.dashboard import DASHBOARD_HTML

_ROOT = Path(__file__).resolve().parent.parent
_QUICKSTART = _ROOT / "scripts" / "quickstart.py"
_VERIFY = _ROOT / "scripts" / "verify_onboarding.py"


def _load_quickstart():
    spec = importlib.util.spec_from_file_location("quickstart", _QUICKSTART)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _child_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


# --- python interpreter detection -------------------------------------------


def test_detects_current_supported_interpreter():
    choice = ob.detect_supported_python(
        current_version=(3, 12), current_executable="/usr/bin/python3.12"
    )
    assert choice.is_current and choice.version == "3.12"
    assert choice.executable == "/usr/bin/python3.12"


def test_falls_back_to_supported_on_path_when_current_unsupported():
    def which(name: str):
        return f"/usr/bin/{name}" if name == "python3.11" else None

    choice = ob.detect_supported_python(current_version=(3, 10), which=which)
    assert not choice.is_current
    assert choice.version == "3.11" and choice.executable == "/usr/bin/python3.11"


def test_prefers_newest_supported_on_path():
    choice = ob.detect_supported_python(
        current_version=(3, 9), which=lambda name: f"/usr/bin/{name}"
    )
    assert choice.version == "3.12"  # newest of 3.11/3.12 wins


def test_rejects_unsupported_with_short_message():
    with pytest.raises(ob.BootstrapError) as excinfo:
        ob.detect_supported_python(current_version=(3, 10), which=lambda _n: None)
    msg = str(excinfo.value)
    assert "not supported" in msg
    assert "3.11" in msg and "3.12" in msg
    assert "datetime.UTC" in msg  # the exact fresh-clone failure mode
    assert len(msg.splitlines()) <= 4  # short, never a traceback


@pytest.mark.parametrize(
    "platform,expected",
    [("darwin", "brew"), ("win32", "python.org"), ("linux", "apt")],
)
def test_unsupported_message_is_os_appropriate(platform, expected):
    msg = ob.unsupported_python_message("3.10", platform=platform)
    assert expected in msg


def test_unsupported_message_points_at_found_interpreter():
    msg = ob.unsupported_python_message("3.10", found="/usr/bin/python3.12")
    assert "/usr/bin/python3.12" in msg


# --- server URL parsing + readiness -----------------------------------------


def test_parse_serve_url_extracts_bound_address():
    line = "cost-router serving on http://127.0.0.1:8123 (offline)"
    assert ob.parse_serve_url(line) == "http://127.0.0.1:8123"


def test_parse_serve_url_handles_rebound_port_and_garbage():
    assert ob.parse_serve_url("cost-router serving on http://127.0.0.1:8001 (offline)").endswith(
        ":8001"
    )
    assert ob.parse_serve_url("nothing to see here") is None


def test_wait_for_http_ready_returns_on_success(monkeypatch):
    calls = {"n": 0}

    def fake_ok(url, timeout=2.0):
        calls["n"] += 1
        return calls["n"] >= 3  # ready on the third poll

    monkeypatch.setattr(ob, "http_ok", fake_ok)
    elapsed = ob.wait_for_http_ready(
        "http://x/healthz", timeout=5, interval=0, sleep=lambda _s: None
    )
    assert elapsed >= 0 and calls["n"] == 3


def test_wait_for_http_ready_times_out(monkeypatch):
    monkeypatch.setattr(ob, "http_ok", lambda *a, **k: False)
    with pytest.raises(ob.ReadinessTimeout):
        ob.wait_for_http_ready("http://x/healthz", timeout=0.2, interval=0.05, sleep=time.sleep)


# --- success screen + Star CTA contract (§2.5) ------------------------------


def test_dashboard_ships_success_screen_and_star_cta():
    assert ob.verify_success_markup(DASHBOARD_HTML) == []
    assert ob.verify_star_cta(DASHBOARD_HTML) == []


def test_success_panel_ships_hidden_so_cta_appears_only_after_pass():
    # "after a PASS" is enforced structurally: the panel is hidden in the static
    # markup and only JS reveals it once the offline replay completes.
    import re

    panel = re.search(r"<section\b[^>]*id=\"journeyPanel\"[^>]*>", DASHBOARD_HTML)
    assert panel and "hidden" in panel.group(0)


def test_star_cta_requires_https_repo_url():
    broken = DASHBOARD_HTML.replace(
        "https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing",
        "http://github.com/hyeonsangjeon/foundry-cost-aware-model-routing",
        1,
    )
    problems = ob.verify_star_cta(broken)
    assert any("https" in p for p in problems)


def test_star_cta_requires_noopener_on_new_tab():
    broken = DASHBOARD_HTML.replace('rel="noopener noreferrer"', 'rel="opener"')
    assert any("noopener" in p for p in ob.verify_star_cta(broken))


def test_success_markup_requires_measured_false_label():
    assert ob.verify_success_markup("<section id=\"journeyPanel\" hidden></section>")


def test_star_cta_absent_is_reported():
    assert ob.verify_star_cta("<a href=\"https://example.com\">x</a>")


# --- hero PASS signal --------------------------------------------------------


def test_hero_json_ok_true_when_ok_and_all_checks_pass():
    assert ob.hero_json_ok({"ok": True, "checks": [{"ok": True}, {"ok": True}]})


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": False, "checks": [{"ok": True}]},
        {"ok": True, "checks": [{"ok": True}, {"ok": False}]},
        {"ok": True, "checks": []},
        {"ok": True},
        "not-a-dict",
    ],
)
def test_hero_json_ok_false_cases(payload):
    assert not ob.hero_json_ok(payload)


# --- process-tree teardown ---------------------------------------------------


def test_terminate_process_tree_kills_child_and_is_idempotent():
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    assert proc.poll() is None
    ob.terminate_process_tree(proc, timeout=5)
    assert proc.poll() is not None
    ob.terminate_process_tree(proc, timeout=5)  # no-op on an already-dead process


# --- time contract constants -------------------------------------------------


def test_time_contract_constants():
    assert ob.HERO_BUDGET_S == 30.0
    assert ob.READY_BUDGET_S == 10.0
    assert ob.RESULT_BUDGET_S == 30.0
    assert ob.RELEASE_BUDGET_S == 600.0


# --- quickstart in-process: readiness timeout -> nonzero + teardown ----------


def test_quickstart_maps_readiness_timeout_to_nonzero_and_tears_down(monkeypatch):
    qs = _load_quickstart()
    torn = {"count": 0}

    def fake_boot(py, host, port, *, tele):
        raise qs.ob.ReadinessTimeout("never ready (injected)")

    def fake_teardown(proc):
        torn["count"] += 1

    monkeypatch.setattr(qs, "boot_dashboard", fake_boot)
    monkeypatch.setattr(qs, "_safe_teardown", fake_teardown)
    monkeypatch.setattr(qs, "run_hero", lambda py, *, tele: {"ok": True, "checks": [{"ok": True}]})

    args = qs._parse_args(["--ci", "--no-install"])
    rc = qs.run(args)
    assert rc == 4  # dashboard-stage failure
    assert torn["count"] == 1  # teardown always attempted


def test_quickstart_reports_cleanup_failure_as_nonzero(monkeypatch):
    qs = _load_quickstart()

    class _FakeProc:
        pass

    def fake_boot(py, host, port, *, tele):
        tele.record("readiness", 0.01, gate=True)
        return _FakeProc(), "http://127.0.0.1:9"

    monkeypatch.setattr(qs, "boot_dashboard", fake_boot)
    monkeypatch.setattr(
        qs, "verify_result", lambda url, *, tele: tele.record("result", 0.0, gate=True)
    )
    monkeypatch.setattr(qs, "run_hero", lambda py, *, tele: {"ok": True, "checks": [{"ok": True}]})

    def boom(proc, timeout=5.0):
        raise qs.ob.CleanupError("process would not die (injected)")

    monkeypatch.setattr(qs.ob, "terminate_process_tree", boom)
    args = qs._parse_args(["--ci", "--no-install"])
    assert qs.run(args) == 5  # cleanup failure is surfaced


# --- subprocess integration: the real headless contract ----------------------


def test_quickstart_ci_no_install_headless_pass_and_clean(tmp_path):
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(_QUICKSTART), "--ci", "--no-install"],
        cwd=str(_ROOT), env=_child_env(), capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    line = next(
        (ln for ln in res.stdout.splitlines() if ln.startswith("ONBOARDING result=pass")), ""
    )
    assert line, res.stdout
    assert "hero_pass=true" in line and "cta_ok=true" in line
    assert "port=" in line
    # no orphan server survived cleanup
    ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True)  # noqa: S603,S607
    assert not [ln for ln in ps.stdout.splitlines() if "router.cli serve" in ln]


def test_verify_onboarding_offline_passes():
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(_VERIFY), "--offline"],
        cwd=str(_ROOT), env=_child_env(), capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "VERIFY ONBOARDING: PASS" in res.stdout
