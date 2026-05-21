from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from craik.contracts.models import ContextRequest, Handoff, SelfAudit
from craik.runtime.work.exit_discipline import build_exit_discipline_check

NOW = datetime(2026, 5, 16, 10, 20, tzinfo=UTC)


def _request(**overrides: object) -> ContextRequest:
    payload = {
        "id": "context_request_release_state",
        "task_id": "task_exit",
        "project_id": "project_exit",
        "requester": "agent:codex",
        "kind": "external_state",
        "status": "open",
        "question": "Did release state change?",
        "needed_for": "Avoid using stale external state.",
        "unknown_id": "unknown_release_state",
        "created_at": NOW,
    }
    payload.update(overrides)
    return ContextRequest.model_validate(payload)


def _handoff(**overrides: object) -> Handoff:
    payload = {
        "id": "handoff_exit",
        "task_id": "task_exit",
        "project_id": "project_exit",
        "agent": "agent:codex",
        "summary": "Completed work.",
        "self_audit": SelfAudit(
            schema_validated=True,
            redaction_reviewed=True,
            receipts_reviewed=True,
            assumptions_reviewed=True,
            validation_recorded=True,
            policy_exceptions_disclosed=True,
        ),
        "tests_run": ["pytest"],
        "risks": [],
        "next_steps": ["Continue."],
        "created_at": NOW,
    }
    payload.update(overrides)
    return Handoff.model_validate(payload)


def test_complete_exit() -> None:
    check = build_exit_discipline_check(_handoff(), task_id="task_exit", created_at=NOW)

    assert check.status == "complete"
    assert check.blocking_reasons == []
    assert check.handoff_id == "handoff_exit"


def test_blocked_exit_with_open_context_request() -> None:
    request = _request()
    check = build_exit_discipline_check(
        _handoff(next_steps=[]),
        task_id="task_exit",
        context_requests=[request],
        unknown_ids=["unknown_release_state"],
        created_at=NOW,
    )

    assert check.status == "blocked"
    assert "Next steps were not recorded." in check.blocking_reasons
    assert "Open context requests remain." in check.blocking_reasons
    assert check.context_request_ids == [request.id]
    assert check.unknown_ids == ["unknown_release_state"]


def test_context_request_handoff_can_be_fulfilled() -> None:
    request = _request(
        status="fulfilled",
        fulfilled_by="user:maintainer",
        fulfilled_at=NOW,
        fulfilled_by_receipt_id="receipt_context_request_fulfilled",
        handoff_id="handoff_exit",
        recovery_session_id="recovery_session_task_exit",
    )

    assert request.status == "fulfilled"
    assert request.handoff_id == "handoff_exit"
    assert request.recovery_session_id == "recovery_session_task_exit"


def test_fulfilled_context_request_requires_fulfillment_details() -> None:
    with pytest.raises(ValidationError, match="fulfilled context requests"):
        _request(status="fulfilled")
