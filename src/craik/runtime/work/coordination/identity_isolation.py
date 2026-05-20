"""Per-agent credential and operator isolation checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from craik.contracts.models import CapabilityReceipt, Handoff, ReceiptResult, ReceiptStatus
from craik.runtime.store import LocalStore


class IdentityIsolationError(RuntimeError):
    """Raised when a consumer identity assignment violates isolation rules."""


@dataclass(frozen=True)
class IdentityIsolationDecision:
    """Validated consumer identity assignment for follow-up agent work."""

    auth_profile_id: str
    operator_subject: str
    operator_issuer: str
    continued_producer_identity: bool
    receipt: CapabilityReceipt


def validate_handoff_consumer_identity(
    store: LocalStore,
    *,
    handoff: Handoff,
    auth_profile_id: str,
    operator_subject: str,
    operator_issuer: str,
    allow_identity_continuation: bool = False,
    identity_continuation_rationale: str | None = None,
) -> IdentityIsolationDecision:
    """Validate and receipt explicit consumer identity for a consumed handoff."""
    if not auth_profile_id:
        raise _denied(
            store,
            handoff=handoff,
            reason="handoff consumption requires --auth-profile-id",
            auth_profile_id=auth_profile_id,
            operator_subject=operator_subject,
            operator_issuer=operator_issuer,
        )
    if not operator_subject or not operator_issuer:
        raise _denied(
            store,
            handoff=handoff,
            reason="handoff consumption requires --operator-subject and --operator-issuer",
            auth_profile_id=auth_profile_id,
            operator_subject=operator_subject,
            operator_issuer=operator_issuer,
        )

    continued = _same_identity(
        handoff=handoff,
        auth_profile_id=auth_profile_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
    )
    if continued and not allow_identity_continuation:
        raise _denied(
            store,
            handoff=handoff,
            reason=(
                "handoff consumer identity matches producer identity; pass "
                "--allow-identity-continuation to make continuation explicit"
            ),
            auth_profile_id=auth_profile_id,
            operator_subject=operator_subject,
            operator_issuer=operator_issuer,
        )
    if continued and not _has_rationale(identity_continuation_rationale):
        raise _denied(
            store,
            handoff=handoff,
            reason="identity continuation requires a non-empty rationale",
            auth_profile_id=auth_profile_id,
            operator_subject=operator_subject,
            operator_issuer=operator_issuer,
            identity_continuation_rationale=identity_continuation_rationale,
        )

    receipt = store.put_receipt(
        _receipt(
            handoff=handoff,
            status="passed",
            reason="Explicit consumer identity assignment accepted.",
            auth_profile_id=auth_profile_id,
            operator_subject=operator_subject,
            operator_issuer=operator_issuer,
            continued_producer_identity=continued,
            identity_continuation_rationale=identity_continuation_rationale,
        )
    )
    return IdentityIsolationDecision(
        auth_profile_id=auth_profile_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        continued_producer_identity=continued,
        receipt=receipt,
    )


def _same_identity(
    *,
    handoff: Handoff,
    auth_profile_id: str,
    operator_subject: str,
    operator_issuer: str,
) -> bool:
    return (
        handoff.auth_profile_id == auth_profile_id
        and handoff.operator_subject == operator_subject
        and handoff.operator_issuer == operator_issuer
    )


def _has_rationale(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _denied(
    store: LocalStore,
    *,
    handoff: Handoff,
    reason: str,
    auth_profile_id: str,
    operator_subject: str,
    operator_issuer: str,
    identity_continuation_rationale: str | None = None,
) -> IdentityIsolationError:
    store.put_receipt(
        _receipt(
            handoff=handoff,
            status="denied",
            reason=reason,
            auth_profile_id=auth_profile_id or None,
            operator_subject=operator_subject or None,
            operator_issuer=operator_issuer or None,
            continued_producer_identity=False,
            identity_continuation_rationale=identity_continuation_rationale,
        )
    )
    return IdentityIsolationError(reason)


def _receipt(
    *,
    handoff: Handoff,
    status: ReceiptStatus,
    reason: str,
    auth_profile_id: str | None,
    operator_subject: str | None,
    operator_issuer: str | None,
    continued_producer_identity: bool,
    identity_continuation_rationale: str | None,
) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=f"receipt_{handoff.id}_identity_isolation_{status}",
        task_id=handoff.task_id,
        actor="craik:identity-isolation",
        capability="handoff.identity.assign",
        target=handoff.id,
        policy_profile="strict",
        fail_open=False,
        reason=reason,
        result=ReceiptResult(
            status=status,
            summary=reason,
            metadata={
                "handoff_id": handoff.id,
                "producer_auth_profile_id": handoff.auth_profile_id,
                "consumer_auth_profile_id": auth_profile_id,
                "producer_operator_subject": handoff.operator_subject,
                "consumer_operator_subject": operator_subject,
                "producer_operator_issuer": handoff.operator_issuer,
                "consumer_operator_issuer": operator_issuer,
                "continued_producer_identity": continued_producer_identity,
                "identity_continuation_rationale": identity_continuation_rationale,
            },
        ),
        redacted=True,
        auth_profile_id=auth_profile_id,
        operator_subject=operator_subject,
        operator_issuer=operator_issuer,
        created_at=datetime.now(UTC),
    )
