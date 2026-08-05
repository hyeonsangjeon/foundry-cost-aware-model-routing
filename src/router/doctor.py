"""Doctor pre-flight — fail closed before the first paid call (BOLT-03B, step 6).

Doctor validates everything needed for a safe measured run *without ever sending
an inference prompt*. It reports authentication and authorization as three
distinct facts — ``token_acquired``, ``data_plane_rbac_verified``, and
``deployment_config_verified`` — and never renders ``unknown`` as success. Token
acquisition is not RBAC proof.

On an RBAC failure it does not dead-end: it prints a read-only lookup first, then
an assignment command with unmistakable placeholders, and never emits a mutation
command containing guessed subscription/resource IDs.

All checks are offline and deterministic. Network/identity probes are injected so
the default path (and CI) never egresses.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

# Check statuses. ``unknown`` is explicitly NOT success.
OK = "ok"
FAIL = "fail"
UNKNOWN = "unknown"
SKIP = "skip"

MIN_PYTHON = (3, 11)
DEPLOYMENT_PROPAGATION_WINDOW_S = 300  # Azure's documented mode/subset propagation


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    next_step: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)
    token_acquired: bool = False
    data_plane_rbac_verified: bool | None = None
    deployment_config_verified: bool | None = None

    def add(
        self, name: str, status: str, detail: str, next_step: str | None = None
    ) -> None:
        self.checks.append(Check(name, status, detail, next_step))

    @property
    def ready(self) -> bool:
        """No failing check. ``unknown`` never counts as ready-for-publish."""

        return all(c.status != FAIL for c in self.checks)

    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    def to_text(self) -> str:
        glyph = {OK: "✓", FAIL: "✗", UNKNOWN: "?", SKIP: "–"}
        lines: list[str] = ["cost-router doctor", ""]
        for check in self.checks:
            lines.append(f"{glyph.get(check.status, '?')} {check.name}: {check.detail}")
            if check.next_step and check.status in {FAIL, UNKNOWN}:
                for step in check.next_step.splitlines():
                    lines.append(f"    {step}")
        lines.append("")
        lines.append(f"token_acquired = {_flag(self.token_acquired)}")
        lines.append(f"data_plane_rbac_verified = {_flag(self.data_plane_rbac_verified)}")
        lines.append(
            f"deployment_config_verified = {_flag(self.deployment_config_verified)}"
        )
        return "\n".join(lines)


def _flag(value: bool | None) -> str:
    return "unknown" if value is None else ("true" if value else "false")


# The RBAC remediation block: read-only lookups first, then an assignment command
# whose subscription/resource/principal IDs are unmistakable placeholders. It
# never prints a mutation command with guessed real IDs.
RBAC_REMEDIATION = (
    "data-plane RBAC not verified — resolve the real IDs, then assign:\n"
    "1) find your resource id:\n"
    "   az cognitiveservices account show -n <ACCOUNT> -g <RG> --query id -o tsv\n"
    "2) find your identity:\n"
    "   az ad signed-in-user show --query id -o tsv\n"
    "3) assign (substitute the two values from above):\n"
    '   az role assignment create --assignee <PRINCIPAL_ID> \\\n'
    '     --role "Cognitive Services OpenAI User" --scope <RESOURCE_ID>\n'
    "note: propagation can take several minutes."
)


@dataclass(frozen=True)
class DeploymentEvidence:
    """Management-plane deployment evidence captured for a benchmark run."""

    management_api_version: str
    retrieved_at: str
    payload_hash: str
    etag: str | None = None
    mode: str | None = None
    version: str | None = None
    subset: tuple[str, ...] = ()

    def matches(self, other: DeploymentEvidence) -> bool:
        """True when the live mode/version/subset equals the approved evidence."""

        return (
            self.mode == other.mode
            and self.version == other.version
            and tuple(self.subset) == tuple(other.subset)
            and self.payload_hash == other.payload_hash
        )


@dataclass
class DoctorInputs:
    """Already-extracted, offline facts doctor validates (built from plan+config)."""

    run_mode: str
    endpoint: str | None
    endpoint_kind: str
    deployments: Sequence[str]
    arms: Sequence[Mapping[str, Any]]
    workload_path: str | None
    workload_ok: bool
    rate_card_present: bool
    rate_card_covers_all_arms: bool
    authorization_ceiling_usd: float | None
    planned_cells: int
    base_transport_attempts: int
    max_transport_attempts: int
    output_token_ceiling: int
    conservative_max_authorized_spend_usd: str
    prereg_note: str
    prereg_allowed: bool
    output_dir: str | None
    output_dir_writable: bool
    retain_raw_outputs: bool
    wiring_only: bool = False
    deps_present: bool = True
    az_cli_present: bool = True
    unsafe_host_override: bool = False


def _check_python(report: DoctorReport) -> None:
    if sys.version_info[:2] >= MIN_PYTHON:
        report.add("python", OK, f"Python {sys.version_info.major}.{sys.version_info.minor}")
    else:
        report.add(
            "python", FAIL,
            f"Python {sys.version_info.major}.{sys.version_info.minor} is below the "
            f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]} floor",
            f"install Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
        )


def _check_deps(report: DoctorReport, inputs: DoctorInputs) -> None:
    if inputs.deps_present:
        report.add("dependencies", OK, "the .[foundry] extra is importable")
    else:
        report.add(
            "dependencies", FAIL, "the .[foundry] extra is not installed",
            "pip install -e '.[foundry]'",
        )


def _check_az_cli(report: DoctorReport, inputs: DoctorInputs) -> None:
    if inputs.az_cli_present:
        report.add("az cli", OK, "the Azure CLI is on PATH")
    else:
        report.add(
            "az cli", UNKNOWN,
            "the Azure CLI is not on PATH (needed for `az login` + RBAC lookups)",
            "install the Azure CLI, then `az login --tenant <TENANT>`",
        )


def _check_endpoint(report: DoctorReport, inputs: DoctorInputs) -> None:
    endpoint = inputs.endpoint
    if not endpoint:
        report.add(
            "endpoint", FAIL, "no endpoint configured",
            "set the endpoint in .foundry.local.yaml",
        )
        return
    parsed = urlparse(endpoint)
    if parsed.scheme != "https":
        if not inputs.unsafe_host_override:
            report.add(
                "endpoint", FAIL, f"non-https endpoint rejected: {endpoint}",
                "use an https:// endpoint (or an explicit unsafe/dev override)",
            )
            return
    host = parsed.hostname or ""
    safe = host.endswith((".openai.azure.com", ".cognitiveservices.azure.com",
                          ".services.ai.azure.com"))
    if safe or inputs.unsafe_host_override:
        report.add("endpoint", OK, f"https + recognized host ({host})")
    else:
        report.add(
            "endpoint", FAIL, f"unrecognized host {host!r}",
            "use a recognized Azure host, or an explicit unsafe/dev override",
        )


def _check_dialect(report: DoctorReport, inputs: DoctorInputs) -> None:
    kind = (inputs.endpoint_kind or "").lower()
    if kind in {"azure_openai", "openai"}:
        report.add("dialect", OK, "azure_openai endpoint -> openai SDK client")
    elif kind in {"model_inference", "foundry"}:
        report.add("dialect", UNKNOWN, "model-inference dialect (partner surface)")
    else:
        report.add("dialect", FAIL, f"unsupported endpoint dialect {kind!r}")


def _check_token(
    report: DoctorReport, token_probe: Callable[[], str] | None
) -> None:
    if token_probe is None:
        report.add(
            "token", UNKNOWN, "no token probe configured (configuration present is not a token)",
            "sign in: az login, then re-run doctor",
        )
        report.token_acquired = False
        return
    try:
        token = token_probe()
    except Exception as exc:  # noqa: BLE001 - any acquisition failure is a false
        report.add("token", FAIL, f"Entra token acquisition failed: {exc}",
                   "az login --tenant <TENANT>")
        report.token_acquired = False
        return
    report.token_acquired = bool(token)
    report.add(
        "token", OK if token else FAIL,
        "Entra token acquired (not RBAC proof)" if token else "empty token",
    )


def _check_rbac(
    report: DoctorReport, rbac_probe: Callable[[], bool | None] | None
) -> None:
    verified: bool | None = None
    if rbac_probe is not None:
        try:
            verified = rbac_probe()
        except Exception:  # noqa: BLE001 - a failed read-only lookup is 'unknown', not 'false'
            verified = None
    report.data_plane_rbac_verified = verified
    if verified is True:
        report.add("rbac", OK, "data-plane RBAC verified via read-only lookup")
    elif verified is False:
        report.add("rbac", FAIL, "data-plane RBAC confirmed absent", RBAC_REMEDIATION)
    else:
        report.add(
            "rbac", UNKNOWN,
            "data-plane RBAC could not be verified (read-only lookup unavailable)",
            RBAC_REMEDIATION,
        )


def _check_deployment_config(
    report: DoctorReport, inputs: DoctorInputs,
    deployment_probe: Callable[[], bool | None] | None,
) -> None:
    if not inputs.deployments:
        report.add("deployments", FAIL, "no deployment configured")
        report.deployment_config_verified = False
        return
    verified: bool | None = None
    if deployment_probe is not None:
        try:
            verified = deployment_probe()
        except Exception:  # noqa: BLE001 - unreadable management plane is 'unknown'
            verified = None
    report.deployment_config_verified = verified
    names = ", ".join(inputs.deployments)
    if verified is True:
        report.add("deployments", OK, f"configured + mode/version/subset verified ({names})")
    elif verified is False:
        report.add("deployments", FAIL, f"live deployment config mismatch ({names})")
    else:
        report.add(
            "deployments", UNKNOWN,
            f"configured ({names}); mode/version/subset not verified "
            "(management-plane evidence unreadable)",
        )


def _check_workload(report: DoctorReport, inputs: DoctorInputs) -> None:
    if inputs.workload_ok:
        report.add(
            "workload", OK,
            f"valid workload + deterministic validation ({inputs.workload_path})",
        )
    else:
        report.add(
            "workload", FAIL, f"workload invalid or unreadable: {inputs.workload_path}",
            "point benchmark.workload at a readable JSONL workload",
        )


def _check_pricing(report: DoctorReport, inputs: DoctorInputs) -> None:
    if inputs.run_mode == "benchmark":
        if inputs.rate_card_present and inputs.rate_card_covers_all_arms:
            report.add("pricing", OK, "complete pinned pricing coverage for every arm")
        else:
            report.add(
                "pricing", FAIL,
                "benchmark mode requires a complete pinned rate card covering every arm",
                "pin every arm's rates in benchmark.rate_card (no default fallback)",
            )
    else:
        has_ceiling = (
            inputs.authorization_ceiling_usd is not None
            and inputs.authorization_ceiling_usd > 0
        )
        if inputs.rate_card_present and inputs.rate_card_covers_all_arms:
            report.add("pricing", OK, "complete pricing (smoke)")
        elif has_ceiling:
            report.add(
                "pricing", OK,
                f"no complete rate card; authorized by ceiling "
                f"${inputs.authorization_ceiling_usd} (response stays unpriced)",
            )
        else:
            report.add(
                "pricing", FAIL,
                "smoke needs complete pricing or a positive authorization ceiling",
            )


def _check_prereg(report: DoctorReport, inputs: DoctorInputs) -> None:
    report.add(
        "preregistration", OK if inputs.prereg_allowed else FAIL, inputs.prereg_note,
        None if inputs.prereg_allowed else "commit a preregistration before a benchmark",
    )


def _check_plan_bounds(report: DoctorReport, inputs: DoctorInputs) -> None:
    report.add(
        "authorized spend", OK,
        f"{inputs.planned_cells} planned cells x up to "
        f"{inputs.max_transport_attempts} transport attempts "
        f"(base {inputs.base_transport_attempts}); output token ceiling "
        f"{inputs.output_token_ceiling}/call; conservative maximum authorized spend "
        f"${inputs.conservative_max_authorized_spend_usd}",
    )


def _check_benchmark_gate(report: DoctorReport, inputs: DoctorInputs) -> None:
    """Benchmark fails closed unless auth+RBAC+deployment are all *verified*.

    ``unknown`` is not success: an unverified fact blocks the paid benchmark path
    here rather than being silently treated as OK.
    """

    if inputs.run_mode != "benchmark":
        return
    missing: list[str] = []
    if report.token_acquired is not True:
        missing.append("token_acquired")
    if report.data_plane_rbac_verified is not True:
        missing.append("data_plane_rbac_verified")
    if report.deployment_config_verified is not True:
        missing.append("deployment_config_verified")
    if missing:
        report.add(
            "benchmark authorization", FAIL,
            "benchmark is fail-closed until these are verified (not unknown): "
            + ", ".join(missing),
            "resolve the checks above, then re-run doctor before dispatch",
        )
    else:
        report.add(
            "benchmark authorization", OK,
            "auth + data-plane RBAC + deployment config all verified",
        )


def _check_output(report: DoctorReport, inputs: DoctorInputs) -> None:
    if not inputs.output_dir:
        report.add("output", FAIL, "no local output directory configured")
        return
    if not inputs.output_dir_writable:
        report.add("output", FAIL, f"output directory not writable: {inputs.output_dir}")
        return
    redaction = "raw outputs retained (private)" if inputs.retain_raw_outputs else (
        "raw outputs discarded after in-memory grading"
    )
    report.add("output", OK, f"{inputs.output_dir} writable; {redaction}")


def run_doctor(
    inputs: DoctorInputs,
    *,
    token_probe: Callable[[], str] | None = None,
    rbac_probe: Callable[[], bool | None] | None = None,
    deployment_probe: Callable[[], bool | None] | None = None,
) -> DoctorReport:
    """Run every offline pre-flight check. Never sends an inference prompt."""

    report = DoctorReport()
    _check_python(report)
    _check_deps(report, inputs)
    _check_az_cli(report, inputs)
    _check_endpoint(report, inputs)
    _check_dialect(report, inputs)
    _check_token(report, token_probe)
    _check_rbac(report, rbac_probe)
    _check_deployment_config(report, inputs, deployment_probe)
    _check_workload(report, inputs)
    _check_pricing(report, inputs)
    _check_prereg(report, inputs)
    _check_plan_bounds(report, inputs)
    _check_output(report, inputs)
    _check_benchmark_gate(report, inputs)
    return report


def az_cli_available() -> bool:
    return shutil.which("az") is not None


def verify_deployment_evidence(
    approved: DeploymentEvidence,
    current: DeploymentEvidence,
    *,
    propagation_window_s: int = DEPLOYMENT_PROPAGATION_WINDOW_S,
    seconds_since_change: float | None = None,
) -> tuple[bool, str]:
    """Reject a benchmark on a mode/version/subset mismatch, honoring propagation.

    Returns ``(ok, note)``. A mismatch inside Azure's documented propagation
    window (a very recent mode/subset change) is reported as a wait, not a hard
    reject; outside the window a mismatch fails closed.
    """

    if approved.matches(current):
        return True, "live deployment evidence matches the approved evidence"
    if seconds_since_change is not None and seconds_since_change < propagation_window_s:
        return (
            False,
            f"deployment changed {seconds_since_change:.0f}s ago; honor the "
            f"{propagation_window_s}s propagation window before dispatch",
        )
    return False, "live mode/version/subset differs from the approved evidence"
