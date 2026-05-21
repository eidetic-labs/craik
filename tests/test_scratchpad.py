from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from craik.contracts.models import ScratchpadRecord, UnknownRecord
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore
from craik.runtime.work.scratchpad import active_scratchpad_records, unknown_summaries

NOW = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)


def _store(tmp_path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _scratchpad(**overrides: object) -> ScratchpadRecord:
    payload = {
        "id": "scratchpad_active",
        "task_id": "task_scratchpad",
        "project_id": "project_scratchpad",
        "owner": "agent:codex",
        "status": "active",
        "note": "Temporary implementation note.",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    }
    payload.update(overrides)
    return ScratchpadRecord.model_validate(payload)


def _unknown(**overrides: object) -> UnknownRecord:
    payload = {
        "id": "unknown_release_state",
        "task_id": "task_scratchpad",
        "project_id": "project_scratchpad",
        "owner": "agent:codex",
        "status": "unresolved",
        "question": "Did the external release state change?",
        "needed_resolution": "external_wait",
        "next_action": "Check the release source before relying on prior state.",
        "created_at": NOW,
    }
    payload.update(overrides)
    return UnknownRecord.model_validate(payload)


def test_active_and_expired_scratchpad_records(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        active = _scratchpad()
        expired = _scratchpad(
            id="scratchpad_expired",
            created_at=NOW - timedelta(hours=2),
            expires_at=NOW - timedelta(minutes=1),
        )
        store.put_scratchpad_record(active)
        store.put_scratchpad_record(expired)

        assert active_scratchpad_records(store, "task_scratchpad", now=NOW) == [active]
    finally:
        store.close()


def test_unresolved_and_resolved_unknowns_surface_summaries(tmp_path) -> None:
    store = _store(tmp_path)
    try:
        unresolved = _unknown()
        resolved = _unknown(
            id="unknown_resolved",
            status="resolved",
            resolved_answer="No change.",
            resolved_at=NOW + timedelta(minutes=5),
            resolved_by_receipt_id="receipt_unknown_resolved",
        )
        store.put_unknown_record(unresolved)
        store.put_unknown_record(resolved)

        assert unknown_summaries(store, "task_scratchpad") == [
            "Unknown unresolved: Did the external release state change? "
            "Next action: Check the release source before relying on prior state."
        ]
    finally:
        store.close()


def test_scratchpad_requires_future_expiry() -> None:
    with pytest.raises(ValidationError, match="scratchpad expires_at"):
        _scratchpad(expires_at=NOW)


def test_resolved_unknown_requires_answer_and_timestamp() -> None:
    with pytest.raises(ValidationError, match="resolved unknowns require"):
        _unknown(status="resolved")
