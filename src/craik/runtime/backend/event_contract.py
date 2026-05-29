"""Gateway event contract validation shared by Python backend emitters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from craik.runtime.backend.events import BackendEvent

KNOWN_EVENT_TYPES = {
    "prompt.submitted",
    "approval.resolved",
    "session.ready",
    "session.status",
    "session.history",
    "slash.completed",
    "slash.catalog",
    "model.changed",
    "run.interrupt.requested",
    "run.started",
    "run.working",
    "run.progress",
    "run.event",
    "tool.used",
    "file.changed",
    "approval.requested",
    "approval.denied",
    "model.selected",
    "receipt.created",
    "run.output",
    "run.completed",
    "error",
}


@dataclass(frozen=True)
class GatewayEventContractIssue:
    """One validation issue for a normalized Gateway event."""

    event_index: int
    event_type: str
    message: str


def validate_gateway_event(
    event: BackendEvent | dict[str, Any],
    *,
    event_index: int = 0,
) -> list[GatewayEventContractIssue]:
    """Return contract issues for one Gateway event payload."""
    payload = event.as_dict() if isinstance(event, BackendEvent) else event
    event_type = payload.get("type")
    event_type_text = event_type if isinstance(event_type, str) else "<missing>"
    issues: list[GatewayEventContractIssue] = []

    if event_type_text not in KNOWN_EVENT_TYPES:
        issues.append(
            GatewayEventContractIssue(
                event_index,
                event_type_text,
                f"unsupported event type `{event_type_text}`",
            )
        )
        return issues

    data = payload.get("data")
    if not isinstance(data, dict):
        issues.append(
            GatewayEventContractIssue(
                event_index,
                event_type_text,
                "event data must be a JSON object",
            )
        )
        return issues

    if event_type_text == "prompt.submitted":
        _require_string(issues, event_index, event_type_text, data, "prompt_preview")
    elif event_type_text == "session.ready":
        _require_string(issues, event_index, event_type_text, data, "transport")
    elif event_type_text == "session.status":
        _require_string(issues, event_index, event_type_text, data, "state")
    elif event_type_text == "session.history":
        _require_array(issues, event_index, event_type_text, data, "receipts")
    elif event_type_text == "model.changed":
        _require_string(issues, event_index, event_type_text, data, "model")
    elif event_type_text == "model.selected":
        _require_one_string(
            issues,
            event_index,
            event_type_text,
            data,
            ("backend", "profile.backend"),
            "backend or profile.backend",
        )
    elif event_type_text == "run.working":
        _require_string(issues, event_index, event_type_text, data, "backend")
        _require_string(issues, event_index, event_type_text, data, "phase")
    elif event_type_text == "run.progress":
        _require_string(issues, event_index, event_type_text, data, "message")
    elif event_type_text == "run.started":
        _require_run_id(issues, event_index, event_type_text, payload)
    elif event_type_text == "tool.used":
        _require_string(issues, event_index, event_type_text, data, "tool")
        _require_one_string(
            issues,
            event_index,
            event_type_text,
            data,
            ("target", "command", "message"),
            "target, command, or message",
        )
    elif event_type_text == "file.changed":
        _require_string(issues, event_index, event_type_text, data, "target")
        _require_one_string(
            issues,
            event_index,
            event_type_text,
            data,
            ("text", "message"),
            "text or message",
        )
    elif event_type_text == "approval.requested":
        _require_string(issues, event_index, event_type_text, data, "message")
        _require_one_string(
            issues,
            event_index,
            event_type_text,
            data,
            ("tool", "target", "reason"),
            "tool, target, or reason",
        )
    elif event_type_text == "approval.resolved":
        _require_string(issues, event_index, event_type_text, data, "approval_id")
        _require_string(issues, event_index, event_type_text, data, "decision")
    elif event_type_text == "receipt.created":
        _require_run_id(issues, event_index, event_type_text, payload)
        _require_string(issues, event_index, event_type_text, data, "receipt_id")
    elif event_type_text == "run.output":
        _require_run_id(issues, event_index, event_type_text, payload)
        _require_string(issues, event_index, event_type_text, data, "summary")
    elif event_type_text == "run.completed":
        _require_run_id(issues, event_index, event_type_text, payload)
        _require_string(issues, event_index, event_type_text, data, "status")
    elif event_type_text == "run.event":
        _require_one_string(
            issues,
            event_index,
            event_type_text,
            data,
            ("text", "message"),
            "text or message",
        )
    elif event_type_text == "slash.completed":
        _require_one_present(
            issues,
            event_index,
            event_type_text,
            data,
            ("text", "payload"),
            "text or payload",
        )
    elif event_type_text == "slash.catalog":
        _require_array(issues, event_index, event_type_text, data, "commands")
    elif event_type_text == "run.interrupt.requested":
        _require_run_id(issues, event_index, event_type_text, payload)
    elif event_type_text in {"approval.denied", "error"}:
        _require_string(issues, event_index, event_type_text, data, "message")

    return issues


def validate_gateway_events(
    events: list[BackendEvent | dict[str, Any]],
) -> list[GatewayEventContractIssue]:
    """Return contract issues for a sequence of Gateway events."""
    return [
        issue
        for index, event in enumerate(events)
        for issue in validate_gateway_event(event, event_index=index)
    ]


def format_gateway_event_contract_issues(
    issues: list[GatewayEventContractIssue],
) -> str:
    """Render contract issues for logs, errors, and tests."""
    return "; ".join(
        f"event {issue.event_index} `{issue.event_type}`: {issue.message}"
        for issue in issues
    )


def _require_run_id(
    issues: list[GatewayEventContractIssue],
    event_index: int,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        issues.append(GatewayEventContractIssue(event_index, event_type, "run_id is required"))


def _require_string(
    issues: list[GatewayEventContractIssue],
    event_index: int,
    event_type: str,
    data: dict[str, Any],
    path: str,
) -> None:
    value = _value_at(data, path)
    if not isinstance(value, str) or not value.strip():
        issues.append(
            GatewayEventContractIssue(
                event_index,
                event_type,
                f"data.{path} must be a non-empty string",
            )
        )


def _require_array(
    issues: list[GatewayEventContractIssue],
    event_index: int,
    event_type: str,
    data: dict[str, Any],
    path: str,
) -> None:
    if not isinstance(_value_at(data, path), list):
        issues.append(
            GatewayEventContractIssue(
                event_index,
                event_type,
                f"data.{path} must be an array",
            )
        )


def _require_one_string(
    issues: list[GatewayEventContractIssue],
    event_index: int,
    event_type: str,
    data: dict[str, Any],
    paths: tuple[str, ...],
    label: str,
) -> None:
    if any(isinstance(value := _value_at(data, path), str) and value.strip() for path in paths):
        return
    issues.append(
        GatewayEventContractIssue(
            event_index,
            event_type,
            f"data must include non-empty {label}",
        )
    )


def _require_one_present(
    issues: list[GatewayEventContractIssue],
    event_index: int,
    event_type: str,
    data: dict[str, Any],
    keys: tuple[str, ...],
    label: str,
) -> None:
    if any(key in data for key in keys):
        return
    issues.append(
        GatewayEventContractIssue(
            event_index,
            event_type,
            f"data must include {label}",
        )
    )


def _value_at(data: dict[str, Any], path: str) -> object:
    value: object = data
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value
