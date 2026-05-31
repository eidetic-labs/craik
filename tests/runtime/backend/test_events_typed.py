"""Tests for typed payload builders on top of BackendEvent."""

from __future__ import annotations

from craik.runtime.backend.events import (
    approval_requested_event,
    approval_resolved_event,
    assistant_text_event,
    error_event,
    receipt_event,
    run_completed_event,
    run_started_event,
    tool_event,
)


def test_receipt_event_shape():
    ev = receipt_event(
        receipt_id="r1",
        run_id="run1",
        task_id="t1",
        source="anthropic-cli",
        purpose="execution",
        execution="delegated-observed",
        mode="ask",
        decision="allow",
        decided_by="operator",
    )
    d = ev.as_dict()
    assert d["type"] == "receipt.created"
    assert d["source"] == "anthropic-cli"  # originating adapter — on the envelope
    assert d["data"] == {
        "receipt_id": "r1",
        "purpose": "execution",
        "execution": "delegated-observed",
        "mode": "ask",
        "decision": "allow",
        "decided_by": "operator",
    }
    assert d["run_id"] == "run1" and d["task_id"] == "t1"


def test_tool_event_shape():
    ev = tool_event(
        tool="Bash",
        source="anthropic-cli",
        run_id="run1",
        task_id="t1",
        command="ls -la",
    )
    d = ev.as_dict()
    assert d["type"] == "tool.used"
    assert d["source"] == "anthropic-cli"
    assert d["data"]["tool"] == "Bash"
    assert d["data"]["command"] == "ls -la"
    assert d["run_id"] == "run1"


def test_assistant_text_event_shape():
    ev = assistant_text_event(text="hello world", source="anthropic-cli", run_id="run1")
    d = ev.as_dict()
    assert d["type"] == "assistant_text"
    assert d["source"] == "anthropic-cli"
    assert d["data"] == {"text": "hello world"}


def test_approval_requested_event_shape():
    ev = approval_requested_event(
        message="Allow Bash?",
        source="anthropic-cli",
        run_id="run1",
        tool="Bash",
    )
    d = ev.as_dict()
    assert d["type"] == "approval.requested"
    assert d["source"] == "anthropic-cli"
    assert d["data"]["message"] == "Allow Bash?"
    assert d["data"]["tool"] == "Bash"


def test_approval_resolved_event_shape():
    ev = approval_resolved_event(
        approval_id="a1",
        decision="allow",
        source="anthropic-cli",
        run_id="run1",
        decided_by="operator",
        mode="ask",
    )
    d = ev.as_dict()
    assert d["type"] == "approval.resolved"
    assert d["source"] == "anthropic-cli"
    assert d["data"] == {
        "approval_id": "a1",
        "decision": "allow",
        "decided_by": "operator",
        "mode": "ask",
    }


def test_run_started_event_shape():
    ev = run_started_event(source="anthropic-cli", run_id="run1", task_id="t1")
    d = ev.as_dict()
    assert d["type"] == "run.started"
    assert d["source"] == "anthropic-cli"
    assert d["run_id"] == "run1"


def test_run_completed_event_shape():
    ev = run_completed_event(status="ok", source="anthropic-cli", run_id="run1")
    d = ev.as_dict()
    assert d["type"] == "run.completed"
    assert d["source"] == "anthropic-cli"
    assert d["data"]["status"] == "ok"
    assert d["run_id"] == "run1"


def test_error_event_shape():
    ev = error_event(message="boom", source="gateway", run_id="run1")
    d = ev.as_dict()
    assert d["type"] == "error"
    assert d["source"] == "gateway"
    assert d["data"]["message"] == "boom"


def test_source_default_on_dataclass_is_gateway():
    from craik.runtime.backend.events import BackendEvent

    ev = BackendEvent(type="session.ready")
    assert ev.as_dict()["source"] == "gateway"


def test_event_type_literal_matches_contract():
    """The BackendEventType vocabulary and the contract must not drift apart.

    Adapters add event types over time; this locks the Literal and the
    machine-readable contract to exactly the same set in both directions.
    """
    from typing import get_args

    from craik.runtime.backend.event_contract import known_event_types
    from craik.runtime.backend.events import BackendEventType

    assert set(get_args(BackendEventType)) == known_event_types()
