"""Versioned pricing annotations for Model Router-derived cost.

Azure AI Foundry Model Router pricing is composite: a router input-token markup
plus the resolved underlying model's input and output charges. The measured
artifacts committed to this repository priced routed calls at the resolved
model's rate alone, so every Model Router-derived amount in them omits a billed
component and is incomplete rather than merely approximate.

Those artifacts are evidence, so they stay byte-identical. Instead of editing
them, a versioned annotation records what is incomplete, why, and what may no
longer be claimed. Every reader-facing renderer, snapshot publisher, replay
summary, static build, and CLI display loads this annotation and **fails
closed**: a missing, malformed, or hash-mismatched annotation withholds Model
Router cost and savings output instead of publishing it as though it were
complete.

Direct-model arms are not affected. They address a single model deployment and
are never charged a router input-token markup, so this annotation never
downgrades them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "AnnotationError",
    "AnnotatedArtifact",
    "RouterPricingAnnotation",
    "DEFAULT_ANNOTATION_RELPATH",
    "ANNOTATION_SCHEMA_VERSION",
    "load_router_pricing_annotation",
    "router_cost_disclosure",
    "savings_claim_allowed",
]

ANNOTATION_SCHEMA_VERSION = 1

DEFAULT_ANNOTATION_RELPATH = Path("samples/annotations/legacy-router-pricing.annotation.json")

#: Strictest possible stance, used when no valid annotation can be loaded.
_FAILSAFE_DISCLOSURE: dict[str, Any] = {
    "annotation_available": False,
    "annotation_id": None,
    "annotation_version": None,
    "reason_code": "annotation_unavailable",
    "reason": (
        "No valid Model Router pricing annotation could be loaded, so Model Router-derived "
        "cost cannot be shown as complete."
    ),
    "pricing_incomplete": True,
    "publishable": False,
    "savings_claim_allowed": False,
    "repriced": False,
    "affected_arms": ("router",),
    "affected_deployments": ("model-router",),
    "unaffected_arms": (),
    "label": "pricing annotation unavailable — Model Router cost withheld",
    "short": (
        "Model Router-derived cost is withheld because its pricing annotation is missing, "
        "malformed, or does not match the artifacts it annotates."
    ),
    "withheld": "withheld — Model Router pricing annotation unavailable",
    "authority": None,
    "error": None,
}


class AnnotationError(RuntimeError):
    """Raised when an annotation is missing, malformed, or does not match its artifacts."""


@dataclass(frozen=True)
class AnnotatedArtifact:
    """One tracked artifact whose Model Router-derived cost this annotation covers."""

    path: str
    role: str
    sha256: str
    size_bytes: int
    immutable: bool
    affected_fields: tuple[str, ...]
    record_hashes: tuple[str, ...] = ()
    chain_head: str | None = None


@dataclass(frozen=True)
class RouterPricingAnnotation:
    """A validated, hash-verified annotation over Model Router-derived cost."""

    annotation_id: str
    annotation_version: int
    issued_at: str
    reason_code: str
    reason: str
    authority: str
    pricing_incomplete: bool
    publishable: bool
    savings_claim_allowed: bool
    repriced: bool
    reprice_reason: str
    label: str
    short: str
    withheld: str
    affected_arms: tuple[str, ...]
    affected_deployments: tuple[str, ...]
    unaffected_arms: tuple[str, ...]
    artifacts: tuple[AnnotatedArtifact, ...]
    source: Path

    def covers_arm(self, arm: str) -> bool:
        """True when ``arm`` produces Model Router-derived cost this annotation covers."""

        return str(arm).strip().lower() in self.affected_arms

    def covers_deployment(self, deployment: str) -> bool:
        """True when ``deployment`` is a Model Router deployment this annotation covers."""

        return str(deployment).strip().lower() in self.affected_deployments

    def to_disclosure(self) -> dict[str, Any]:
        """Serializable disclosure block for a payload, snapshot, or rendered surface."""

        return {
            "annotation_available": True,
            "annotation_id": self.annotation_id,
            "annotation_version": self.annotation_version,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "pricing_incomplete": self.pricing_incomplete,
            "publishable": self.publishable,
            "savings_claim_allowed": self.savings_claim_allowed,
            "repriced": self.repriced,
            "affected_arms": list(self.affected_arms),
            "affected_deployments": list(self.affected_deployments),
            "unaffected_arms": list(self.unaffected_arms),
            "label": self.label,
            "short": self.short,
            "withheld": self.withheld,
            "authority": self.authority,
            "error": None,
        }


def _fail(message: str) -> AnnotationError:
    return AnnotationError(message)


def _require_mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail(f"annotation {what} must be an object")
    return value


def _require_str(data: Mapping[str, Any], key: str, what: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"annotation {what}.{key} must be a non-empty string")
    return value


def _require_bool(data: Mapping[str, Any], key: str, what: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise _fail(f"annotation {what}.{key} must be a boolean")
    return value


def _require_names(data: Mapping[str, Any], key: str, what: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str) or not value:
        raise _fail(f"annotation {what}.{key} must be a non-empty list")
    names = tuple(str(item).strip().lower() for item in value)
    if any(not name for name in names):
        raise _fail(f"annotation {what}.{key} must not contain blank entries")
    return names


def _unaffected_arms(scope: Mapping[str, Any]) -> tuple[str, ...]:
    """Arms the annotation explicitly declares untouched by the pricing defect.

    Direct-model arms address a single deployment and are never charged the router
    input-token markup, so their amounts must never be downgraded by this annotation.
    Declaring them here lets every consumer state that positively instead of
    inferring it. Absent or malformed means "claim nothing".
    """

    affected = set(_require_names(scope, "affected_arms", "scope"))
    unaffected = scope.get("unaffected")
    if not isinstance(unaffected, Mapping):
        return ()
    arms = unaffected.get("arms")
    if not isinstance(arms, Sequence) or isinstance(arms, str):
        return ()
    names = tuple(str(item).strip().lower() for item in arms if str(item).strip())
    overlap = sorted(affected.intersection(names))
    if overlap:
        raise _fail(
            "annotation scope.unaffected.arms overlaps scope.affected_arms: "
            + ", ".join(overlap)
        )
    return names


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _sha256(path: Path) -> tuple[str, int]:
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _candidate_roots(root: Path | str | None) -> list[Path]:
    if root is not None:
        return [Path(root).resolve()]
    roots: list[Path] = []
    try:
        from .pipeline import find_samples_root

        roots.append(find_samples_root())
    except Exception:  # pragma: no cover - defensive; falls back to the source tree
        pass
    roots.append(Path(__file__).resolve().parents[2])
    roots.append(Path.cwd().resolve())
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in roots:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _resolve_annotation_path(path: Path | str | None, root: Path | str | None) -> Path:
    if path is not None:
        return Path(path)
    for candidate in _candidate_roots(root):
        resolved = candidate / DEFAULT_ANNOTATION_RELPATH
        if resolved.is_file():
            return resolved
    raise _fail(
        f"Model Router pricing annotation not found at {DEFAULT_ANNOTATION_RELPATH}; "
        "Model Router cost and savings output stays withheld"
    )


def _parse_artifact(entry: Any, index: int) -> AnnotatedArtifact:
    data = _require_mapping(entry, f"evidence_artifacts[{index}]")
    what = f"evidence_artifacts[{index}]"
    sha256 = _require_str(data, "sha256", what)
    if not _is_digest(sha256):
        raise _fail(f"annotation {what}.sha256 must be a lowercase SHA-256 digest")
    size = data.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise _fail(f"annotation {what}.bytes must be a non-negative integer")
    fields = data.get("affected_fields", [])
    if not isinstance(fields, Sequence) or isinstance(fields, str):
        raise _fail(f"annotation {what}.affected_fields must be a list")
    record_hashes = data.get("record_hashes", [])
    if not isinstance(record_hashes, Sequence) or isinstance(record_hashes, str):
        raise _fail(f"annotation {what}.record_hashes must be a list")
    if any(not _is_digest(digest) for digest in record_hashes):
        raise _fail(f"annotation {what}.record_hashes must be lowercase SHA-256 digests")
    chain_head = data.get("chain_head")
    if chain_head is not None and not _is_digest(chain_head):
        raise _fail(f"annotation {what}.chain_head must be a lowercase SHA-256 digest")
    return AnnotatedArtifact(
        path=_require_str(data, "path", what),
        role=_require_str(data, "role", what),
        sha256=sha256,
        size_bytes=size,
        immutable=bool(data.get("immutable", True)),
        affected_fields=tuple(str(field) for field in fields),
        record_hashes=tuple(str(digest) for digest in record_hashes),
        chain_head=str(chain_head) if chain_head is not None else None,
    )


def _verify_artifact(artifact: AnnotatedArtifact, base: Path) -> None:
    target = base / artifact.path
    if not target.is_file():
        raise _fail(f"annotated artifact {artifact.path} is missing")
    digest, size = _sha256(target)
    if digest != artifact.sha256:
        raise _fail(
            f"annotated artifact {artifact.path} does not match its recorded hash "
            f"(expected {artifact.sha256}, found {digest})"
        )
    if size != artifact.size_bytes:
        raise _fail(
            f"annotated artifact {artifact.path} does not match its recorded size "
            f"(expected {artifact.size_bytes} bytes, found {size})"
        )
    if artifact.record_hashes:
        _verify_chain(artifact, target)


def _verify_chain(artifact: AnnotatedArtifact, target: Path) -> None:
    """Cross-check the sealed ledger's own hash chain against the annotation."""

    try:
        records = [
            json.loads(line)
            for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except ValueError as exc:
        raise _fail(f"annotated ledger {artifact.path} is not valid JSONL: {exc}") from exc
    found = tuple(str(record.get("record_hash")) for record in records)
    if found != artifact.record_hashes:
        raise _fail(
            f"annotated ledger {artifact.path} record hashes do not match the annotation"
        )
    if artifact.chain_head is not None and (not found or found[-1] != artifact.chain_head):
        raise _fail(f"annotated ledger {artifact.path} chain head does not match the annotation")


def load_router_pricing_annotation(
    path: Path | str | None = None,
    *,
    root: Path | str | None = None,
    verify_artifacts: bool = True,
) -> RouterPricingAnnotation:
    """Load, validate, and hash-verify the Model Router pricing annotation.

    Raises :class:`AnnotationError` when the annotation is missing, malformed,
    loosened, or no longer matches the artifacts it annotates. Callers that
    render or publish Model Router-derived cost must treat that as a signal to
    withhold the number, never to fall back to the unannotated amount.
    """

    resolved = _resolve_annotation_path(path, root)
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _fail(f"Model Router pricing annotation is unreadable: {exc}") from exc
    except ValueError as exc:
        raise _fail(f"Model Router pricing annotation is not valid JSON: {exc}") from exc
    data = _require_mapping(data, "document")

    schema_version = data.get("schema_version")
    if schema_version != ANNOTATION_SCHEMA_VERSION:
        raise _fail(
            f"unsupported annotation schema_version {schema_version!r}; "
            f"expected {ANNOTATION_SCHEMA_VERSION}"
        )
    annotation_version = data.get("annotation_version")
    if not isinstance(annotation_version, int) or isinstance(annotation_version, bool):
        raise _fail("annotation annotation_version must be an integer")

    effects = _require_mapping(data.get("effects"), "effects")
    pricing_incomplete = _require_bool(effects, "pricing_incomplete", "effects")
    publishable = _require_bool(effects, "publishable", "effects")
    allowed = _require_bool(effects, "savings_claim_allowed", "effects")

    reprice = _require_mapping(data.get("reprice"), "reprice")
    repriced = _require_bool(reprice, "repriced", "reprice")
    _validate_effects(
        repriced=repriced,
        reprice=reprice,
        pricing_incomplete=pricing_incomplete,
        publishable=publishable,
        savings_allowed=allowed,
    )

    disclosure = _require_mapping(data.get("disclosure"), "disclosure")
    scope = _require_mapping(data.get("scope"), "scope")
    artifacts_raw = data.get("evidence_artifacts")
    if not isinstance(artifacts_raw, Sequence) or isinstance(artifacts_raw, str):
        raise _fail("annotation evidence_artifacts must be a list")
    if not artifacts_raw:
        raise _fail("annotation evidence_artifacts must not be empty")
    artifacts = tuple(_parse_artifact(entry, i) for i, entry in enumerate(artifacts_raw))

    annotation = RouterPricingAnnotation(
        annotation_id=_require_str(data, "annotation_id", "document"),
        annotation_version=annotation_version,
        issued_at=_require_str(data, "issued_at", "document"),
        reason_code=_require_str(data, "reason_code", "document"),
        reason=_require_str(data, "reason", "document"),
        authority=_require_str(data, "authority", "document"),
        pricing_incomplete=pricing_incomplete,
        publishable=publishable,
        savings_claim_allowed=allowed,
        repriced=repriced,
        reprice_reason=_require_str(reprice, "reason", "reprice"),
        label=_require_str(disclosure, "label", "disclosure"),
        short=_require_str(disclosure, "short", "disclosure"),
        withheld=_require_str(disclosure, "withheld", "disclosure"),
        affected_arms=_require_names(scope, "affected_arms", "scope"),
        affected_deployments=_require_names(scope, "affected_deployments", "scope"),
        unaffected_arms=_unaffected_arms(scope),
        artifacts=artifacts,
        source=resolved,
    )

    if verify_artifacts:
        base = resolved.parent.parent.parent
        for artifact in annotation.artifacts:
            _verify_artifact(artifact, base)
    return annotation


def _validate_effects(
    *,
    repriced: bool,
    reprice: Mapping[str, Any],
    pricing_incomplete: bool,
    publishable: bool,
    savings_allowed: bool,
) -> None:
    """Reject an annotation that has been loosened without proof of a real reprice.

    Without a proven reprice the three effect flags are fixed. Claiming a
    reprice requires a pinned, historically applicable rate basis and a
    superseding artifact; anything less is treated as tampering.
    """

    if not repriced:
        if not pricing_incomplete or publishable or savings_allowed:
            raise _fail(
                "annotation claims complete or publishable Model Router cost without a "
                "proven reprice; refusing to publish an incomplete amount as complete"
            )
        return
    rate_basis = reprice.get("rate_basis")
    superseding = reprice.get("superseding_artifact")
    if not isinstance(rate_basis, Mapping) or not isinstance(superseding, Mapping):
        raise _fail(
            "annotation claims a reprice without a pinned rate basis and superseding artifact"
        )
    for key in ("router_input_markup", "underlying_rates", "effective_date"):
        if not rate_basis.get(key):
            raise _fail(f"repriced annotation is missing reprice.rate_basis.{key}")
    if not _is_digest(superseding.get("sha256")) or not superseding.get("path"):
        raise _fail("repriced annotation needs a superseding artifact path and SHA-256 digest")


def router_cost_disclosure(
    path: Path | str | None = None,
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Fail-closed disclosure block for any surface that shows Router-derived cost.

    Never raises. When no valid annotation can be loaded it returns the
    strictest possible stance, so a caller that forgets to handle the error
    still cannot publish Model Router cost as complete or savings-capable.
    """

    try:
        annotation = load_router_pricing_annotation(path, root=root)
    except AnnotationError as exc:
        failsafe = dict(_FAILSAFE_DISCLOSURE)
        failsafe["affected_arms"] = list(_FAILSAFE_DISCLOSURE["affected_arms"])
        failsafe["affected_deployments"] = list(_FAILSAFE_DISCLOSURE["affected_deployments"])
        failsafe["unaffected_arms"] = list(_FAILSAFE_DISCLOSURE["unaffected_arms"])
        failsafe["error"] = str(exc)
        return failsafe
    return annotation.to_disclosure()


def savings_claim_allowed(disclosure: Mapping[str, Any]) -> bool:
    """True only when a disclosure explicitly permits a Model Router savings claim."""

    return disclosure.get("savings_claim_allowed") is True
