from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from craik.contracts.models import PluginCapabilityGrant
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _grant(**overrides: object) -> PluginCapabilityGrant:
    payload = {
        "id": "plugin_grant_docs_reconcile",
        "task_id": "task_docs_reconcile",
        "plugin_descriptor_id": "plugin_docs_reconcile",
        "policy_envelope_id": "policy_docs_reconcile",
        "capability": "repo.write.docs",
        "target": {
            "repo": "eidetic-labs/craik",
            "paths": ["docs/**"],
            "exclude": ["docs/adr/**"],
            "metadata": {"scope": "plugin"},
        },
        "operations": ["read", "write"],
        "status": "allowed",
        "approval_required": True,
        "approved_by": "user:maintainer",
        "expires_at": "2026-06-16T16:30:00Z",
        "reason": "Allow docs reconciliation plugin to update docs.",
        "evidence_ids": ["evidence_readme_status"],
        "receipt_ids": ["plugin_receipt_docs_reconcile"],
        "created_at": "2026-05-16T16:30:00Z",
    }
    payload.update(overrides)
    return PluginCapabilityGrant.model_validate(payload)


def test_plugin_capability_grant_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        grant = _grant()
        store.put_plugin_capability_grant(grant)

        assert store.get_plugin_capability_grant(grant.id) == grant
        assert store.list_plugin_capability_grants() == [grant]
    finally:
        store.close()


def test_plugin_capability_grant_supports_allowed_denied_and_expired() -> None:
    allowed = _grant()
    denied = _grant(
        id="plugin_grant_denied",
        status="denied",
        approval_required=False,
        approved_by=None,
        reason="Policy denied plugin write authority.",
    )
    expired = _grant(id="plugin_grant_expired", status="expired")

    assert allowed.status == "allowed"
    assert denied.status == "denied"
    assert expired.status == "expired"


def test_allowed_plugin_grants_require_approval_and_expiry_when_needed() -> None:
    with pytest.raises(ValidationError, match="approved_by"):
        _grant(approved_by=None)

    with pytest.raises(ValidationError, match="expires_at"):
        _grant(expires_at=None)


def test_approval_required_plugin_grants_wait_for_approval() -> None:
    grant = _grant(
        status="approval_required",
        approval_required=True,
        approved_by=None,
        expires_at=None,
    )

    assert grant.status == "approval_required"

    with pytest.raises(ValidationError, match="must set approval_required"):
        _grant(status="approval_required", approval_required=False, approved_by=None)

    with pytest.raises(ValidationError, match="must not include approved_by"):
        _grant(status="approval_required", approval_required=True)


def test_plugin_capability_grants_are_least_privilege() -> None:
    with pytest.raises(ValidationError):
        _grant(operations=[])

    with pytest.raises(ValidationError, match="explicit operations"):
        _grant(operations=["*"])

    with pytest.raises(ValidationError, match="scoped target"):
        _grant(target={"repo": None, "paths": [], "exclude": [], "metadata": {}})

    grant = _grant(operations=["read"])

    assert grant.operations == ["read"]


def test_plugin_capability_grant_permits_only_current_allowed_operations() -> None:
    grant = _grant()

    assert grant.permits_operation("write", at=datetime(2026, 5, 17, tzinfo=UTC)) is True
    assert grant.permits_operation("delete", at=datetime(2026, 5, 17, tzinfo=UTC)) is False

    denied = _grant(status="denied", approval_required=False, approved_by=None)
    pending = _grant(status="approval_required", approved_by=None, expires_at=None)
    expired = _grant(status="expired")
    after_expiry = datetime(2026, 6, 17, tzinfo=UTC)

    assert denied.permits_operation("write", at=datetime(2026, 5, 17, tzinfo=UTC)) is False
    assert pending.permits_operation("write", at=datetime(2026, 5, 17, tzinfo=UTC)) is False
    assert expired.permits_operation("write", at=after_expiry) is False
