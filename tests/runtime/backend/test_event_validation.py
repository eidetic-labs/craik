"""Tests for raise-on-failure contract validation at event emission."""

from __future__ import annotations

import pytest

from craik.runtime.backend.events import (
    BackendEvent,
    EventContractError,
    _validation_enabled,
    approval_requested_event,
    approval_resolved_event,
    assistant_text_event,
    error_event,
    receipt_event,
    run_completed_event,
    run_started_event,
    tool_event,
    validate_event,
)


def test_receipt_missing_receipt_id_raises() -> None:
    """A `receipt.created` event lacking `data.receipt_id` fails validation."""
    ev = BackendEvent(type="receipt.created", run_id="r", data={})
    with pytest.raises(EventContractError):
        validate_event(ev)


def test_well_formed_receipt_passes() -> None:
    """A fully-formed `receipt.created` event validates without raising."""
    ev = receipt_event(
        receipt_id="rcpt-1",
        source="anthropic-cli",
        purpose="edit",
        execution="craik",
        mode="auto",
        decision="allow",
        decided_by="policy",
        run_id="run-1",
    )
    assert validate_event(ev) is None


def test_array_kind_enforced() -> None:
    """The `array` kind fails when the path is not a list and passes when it is."""
    bad = BackendEvent(type="slash.catalog", data={"commands": "not-a-list"})
    with pytest.raises(EventContractError):
        validate_event(bad)

    good = BackendEvent(type="slash.catalog", data={"commands": []})
    assert validate_event(good) is None


def test_one_present_kind_enforced() -> None:
    """The `one_present` kind requires at least one of the listed paths."""
    bad = BackendEvent(type="slash.completed", data={})
    with pytest.raises(EventContractError):
        validate_event(bad)

    good = BackendEvent(type="slash.completed", data={"payload": {"x": 1}})
    assert validate_event(good) is None


def test_one_non_empty_string_kind_enforced() -> None:
    """The `one_non_empty_string` kind requires a non-empty string among paths."""
    bad = BackendEvent(type="run.event", data={"text": "  "})
    with pytest.raises(EventContractError):
        validate_event(bad)

    good = BackendEvent(type="run.event", data={"message": "working"})
    assert validate_event(good) is None


def test_unknown_event_type_raises() -> None:
    """An event whose type is absent from the contract is reported as an issue."""
    ev = BackendEvent(type="future.unknown", data={})  # type: ignore[arg-type]
    with pytest.raises(EventContractError):
        validate_event(ev)


def test_all_builders_validate_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the env-gate on, every builder produces a contract-valid event."""
    monkeypatch.setenv("CRAIK_VALIDATE_EVENTS", "1")
    assert _validation_enabled() is True

    builders = [
        receipt_event(
            receipt_id="rcpt-1",
            source="anthropic-cli",
            purpose="edit",
            execution="craik",
            mode="auto",
            decision="allow",
            decided_by="policy",
            run_id="run-1",
        ),
        tool_event(tool="bash", source="anthropic-cli", command="ls"),
        assistant_text_event(text="hello", source="anthropic-cli"),
        approval_requested_event(message="approve?", source="anthropic-cli", tool="bash"),
        approval_resolved_event(approval_id="appr-1", decision="allow", source="anthropic-cli"),
        run_started_event(source="anthropic-cli", run_id="run-1"),
        run_completed_event(status="ok", source="anthropic-cli", run_id="run-1"),
        error_event(message="boom", source="anthropic-cli"),
    ]
    # Building above already validated under the env-gate; nothing raised.
    assert len(builders) == 8
    for ev in builders:
        validate_event(ev)


def test_env_gate_off_skips_validation_in_builders() -> None:
    """With the env-gate unset, builders do not validate (no behavior change)."""
    assert _validation_enabled() is False
    # `run_started_event` with run_id=None would fail the contract's run_id
    # requirement, but the builder must not validate when the gate is off.
    ev = run_started_event(source="anthropic-cli", run_id=None)
    assert ev.run_id is None
