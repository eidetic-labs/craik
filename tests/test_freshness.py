from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from craik.contracts.models import KnowledgeFreshnessProbe, ToolResultAttestation
from craik.runtime.memory.freshness import (
    attestation_is_fresh,
    classify_probe,
    evaluate_attestation_expiration,
    missing_attestation_warning,
    stale_risk_warnings,
)

NOW = datetime(2026, 5, 16, 9, 20, tzinfo=UTC)


def _attestation(**overrides: object) -> ToolResultAttestation:
    payload = {
        "id": "attestation_gh_issue",
        "task_id": "task_freshness",
        "project_id": "project_freshness",
        "tool_name": "gh",
        "tool_identity": "gh issue view",
        "command": "gh issue view 113 --json title",
        "observed_output_summary": "Issue 113 describes freshness probes.",
        "output_hash": "a" * 64,
        "trust_class": "observed",
        "evidence_ids": ["evidence_gh_issue"],
        "captured_at": NOW,
        "expires_at": NOW + timedelta(hours=2),
    }
    payload.update(overrides)
    return ToolResultAttestation.model_validate(payload)


def _probe(**overrides: object) -> KnowledgeFreshnessProbe:
    payload = {
        "id": "probe_gh_issue",
        "task_id": "task_freshness",
        "project_id": "project_freshness",
        "target": "eidetic-labs/craik#113",
        "kind": "github_state",
        "status": "fresh",
        "trust_class": "observed",
        "observed_output_summary": "Issue state was loaded.",
        "attestation_id": "attestation_gh_issue",
        "captured_at": NOW,
        "expires_at": NOW + timedelta(hours=2),
        "evidence_ids": ["evidence_gh_issue"],
    }
    payload.update(overrides)
    return KnowledgeFreshnessProbe.model_validate(payload)


def test_fresh_attestation_and_probe() -> None:
    attestation = _attestation()
    probe = _probe()

    assert attestation_is_fresh(attestation, now=NOW) is True
    assert classify_probe(probe, now=NOW) == "fresh"
    assert (
        evaluate_attestation_expiration(
            attestation,
            evidence_id="evidence_gh_issue",
            now=NOW,
        ).status
        == "unexpired"
    )


def test_expiring_and_expired_probes_emit_stale_risk_warnings() -> None:
    expiring = _probe(
        id="probe_expiring",
        status="expiring",
        expires_at=NOW + timedelta(minutes=20),
        stale_risk_warning="GitHub issue state expires soon.",
    )
    expired = _probe(
        id="probe_expired",
        status="expired",
        captured_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(minutes=1),
        stale_risk_warning="GitHub issue state is expired.",
    )

    assert classify_probe(expiring, now=NOW) == "expiring"
    assert classify_probe(expired, now=NOW) == "expired"
    assert stale_risk_warnings([expired, expiring], now=NOW) == [
        "GitHub issue state is expired.",
        "GitHub issue state expires soon.",
    ]


def test_expired_attestation_can_be_overridden_explicitly() -> None:
    expired = _attestation(
        captured_at=NOW - timedelta(hours=3),
        expires_at=NOW - timedelta(hours=1),
    )

    blocked = evaluate_attestation_expiration(
        expired,
        evidence_id="evidence_gh_issue",
        now=NOW,
    )
    overridden = evaluate_attestation_expiration(
        expired,
        evidence_id="evidence_gh_issue",
        now=NOW,
        override_reason="Operator refreshed adjacent release state.",
    )

    assert blocked.status == "expired"
    assert blocked.warning == "Evidence evidence_gh_issue expired at 2026-05-16T08:20:00+00:00."
    assert overridden.status == "overridden"
    assert overridden.override_reason == "Operator refreshed adjacent release state."


def test_missing_expiration_is_visible_before_reuse() -> None:
    evaluation = evaluate_attestation_expiration(
        _attestation(expires_at=None),
        evidence_id="evidence_gh_issue",
        now=NOW,
    )

    assert evaluation.status == "missing_expiration"
    assert evaluation.warning == "Evidence evidence_gh_issue has no expiration metadata."


def test_missing_attestation_and_probe() -> None:
    probe = _probe(
        id="probe_missing",
        status="missing",
        attestation_id=None,
        captured_at=None,
        expires_at=None,
        stale_risk_warning="No GitHub issue attestation was captured.",
    )

    assert attestation_is_fresh(None, now=NOW) is False
    assert classify_probe(probe, now=NOW) == "missing"
    assert missing_attestation_warning(
        expected_attestation_id="attestation_missing",
        attestations=[_attestation()],
    ) == "Missing tool result attestation: attestation_missing."


def test_missing_attestation_contract_rejects_evidence_links() -> None:
    with pytest.raises(ValidationError, match="missing attestations"):
        _attestation(status="missing", evidence_ids=["evidence_gh_issue"])


def test_non_fresh_probe_requires_warning() -> None:
    with pytest.raises(ValidationError, match="non-fresh freshness probes"):
        _probe(status="expired", expires_at=NOW + timedelta(hours=2))
