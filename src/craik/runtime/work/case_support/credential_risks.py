"""Credential context evidence and expiry risks for case files."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from craik.contracts.models import EvidenceReference, TaskRequest
from craik.runtime.auth.profile import AuthProfile
from craik.runtime.auth.store import AuthProfileNotFoundError, AuthProfileStore

DEFAULT_EXPECTED_DURATION_MINUTES = 60


def credential_context(
    store: AuthProfileStore,
    task: TaskRequest,
    *,
    now: datetime | None = None,
) -> tuple[list[EvidenceReference], list[str]]:
    """Return credential evidence and expiry risks for a task's auth profile."""
    if task.auth_profile_id is None:
        return [], []
    now = now or datetime.now(UTC)
    try:
        profile = store.get(task.auth_profile_id)
    except AuthProfileNotFoundError:
        return [], [
            f"credential_profile_missing: auth profile {task.auth_profile_id} was referenced "
            "for this task but was not found."
        ]
    expires_at = _credential_expires_at(profile)
    expected_duration = timedelta(
        minutes=task.expected_duration_minutes or DEFAULT_EXPECTED_DURATION_MINUTES
    )
    evidence = [
        EvidenceReference(
            id=f"evidence_{task.id}_auth_profile",
            source="auth_profile_store",
            kind="other",
            locator=profile.id,
            summary="Credential profile selected for the task.",
            captured_at=now,
            metadata={
                "auth_profile_id": profile.id,
                "auth_kind": profile.kind.value,
                "provider_family": profile.provider_family,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "expected_duration_minutes": int(expected_duration.total_seconds() // 60),
            },
        )
    ]
    if expires_at is None or expires_at > now + expected_duration:
        return evidence, []
    return evidence, [
        "credential_expiry_risk: auth profile "
        f"{profile.id} expires at {expires_at.isoformat()} before the expected "
        f"{int(expected_duration.total_seconds() // 60)} minute run completes."
    ]


def _credential_expires_at(profile: AuthProfile) -> datetime | None:
    expires_at = _metadata_datetime(profile.metadata)
    if expires_at is not None:
        return expires_at
    return None


def _metadata_datetime(metadata: dict[str, Any]) -> datetime | None:
    for key in ("expires_at", "expiresAt", "token_expires_at", "tokenExpiresAt"):
        parsed = _parse_datetime(metadata.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None
