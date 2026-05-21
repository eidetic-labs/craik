"""Tool result attestation and knowledge freshness helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from craik.contracts.models import (
    FreshnessProbeStatus,
    KnowledgeFreshnessProbe,
    ToolResultAttestation,
)

EvidenceExpirationStatus = Literal[
    "unexpired",
    "expired",
    "overridden",
    "missing_expiration",
    "missing",
]


@dataclass(frozen=True)
class EvidenceExpirationEvaluation:
    """Deterministic evaluation of whether observed evidence may be reused."""

    evidence_id: str
    status: EvidenceExpirationStatus
    warning: str | None = None
    override_reason: str | None = None


def attestation_is_fresh(
    attestation: ToolResultAttestation | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether an attestation exists and has not expired."""
    if attestation is None or attestation.status != "attested":
        return False
    if attestation.expires_at is None:
        return True
    return attestation.expires_at > (now or datetime.now(UTC))


def evaluate_attestation_expiration(
    attestation: ToolResultAttestation | None,
    *,
    evidence_id: str,
    now: datetime | None = None,
    override_reason: str | None = None,
) -> EvidenceExpirationEvaluation:
    """Evaluate attested evidence reuse without silently trusting stale output."""
    if attestation is None:
        return EvidenceExpirationEvaluation(
            evidence_id=evidence_id,
            status="missing",
            warning=f"Evidence {evidence_id} has no tool result attestation.",
        )
    if attestation.expires_at is None:
        return EvidenceExpirationEvaluation(
            evidence_id=evidence_id,
            status="missing_expiration",
            warning=f"Evidence {evidence_id} has no expiration metadata.",
        )
    current = now or datetime.now(UTC)
    if attestation.expires_at <= current:
        if override_reason:
            return EvidenceExpirationEvaluation(
                evidence_id=evidence_id,
                status="overridden",
                warning=f"Evidence {evidence_id} is expired but was explicitly overridden.",
                override_reason=override_reason,
            )
        return EvidenceExpirationEvaluation(
            evidence_id=evidence_id,
            status="expired",
            warning=f"Evidence {evidence_id} expired at {attestation.expires_at.isoformat()}.",
        )
    return EvidenceExpirationEvaluation(evidence_id=evidence_id, status="unexpired")


def classify_probe(
    probe: KnowledgeFreshnessProbe,
    *,
    now: datetime | None = None,
    expiring_within: timedelta = timedelta(hours=1),
) -> FreshnessProbeStatus:
    """Classify a freshness probe relative to the current time."""
    current = now or datetime.now(UTC)
    if probe.status == "missing" or probe.captured_at is None:
        return "missing"
    if probe.expires_at is None:
        return "fresh"
    if probe.expires_at <= current:
        return "expired"
    if probe.expires_at <= current + expiring_within:
        return "expiring"
    return "fresh"


def stale_risk_warnings(
    probes: list[KnowledgeFreshnessProbe],
    *,
    now: datetime | None = None,
) -> list[str]:
    """Return stale-risk warnings for expiring, expired, or missing probes."""
    warnings: list[str] = []
    for probe in sorted(probes, key=lambda item: item.id):
        status = classify_probe(probe, now=now)
        if status in {"expiring", "expired", "missing"}:
            warnings.append(
                probe.stale_risk_warning
                or f"Freshness probe {probe.id} for {probe.target} is {status}."
            )
    return warnings


def missing_attestation_warning(
    *,
    expected_attestation_id: str,
    attestations: list[ToolResultAttestation],
) -> str | None:
    """Return a stale-risk warning when an expected attestation is absent."""
    if any(attestation.id == expected_attestation_id for attestation in attestations):
        return None
    return f"Missing tool result attestation: {expected_attestation_id}."
