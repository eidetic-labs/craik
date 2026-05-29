"""Claude Code event normalization helpers."""

from __future__ import annotations

import hashlib


def hidden_status_event(*, kind: str, message: str) -> dict[str, object]:
    return {
        "kind": kind,
        "message": message,
        "transcript_visibility": "hidden",
    }


def is_approval_request_event(event: dict[str, object]) -> bool:
    event_type = str(event.get("type") or "").lower()
    subtype = str(event.get("subtype") or "").lower()
    if "approval" in event_type or "permission_request" in event_type:
        return True
    return "approval" in subtype or "permission_request" in subtype


def approval_request_event(event: dict[str, object]) -> dict[str, object]:
    raw_tool = event.get("tool_name") or event.get("tool") or event.get("name")
    raw_target = event.get("target") or event.get("path") or event.get("file_path")
    raw_reason = event.get("reason") or event.get("message") or event.get("description")
    tool = str(raw_tool or "tool")
    target = str(raw_target or "unspecified target")
    reason = str(raw_reason or "Claude Code requested runtime approval.")
    return {
        "kind": "approval_request",
        "approval_id": _approval_request_id(tool=tool, target=target, reason=reason),
        "message": f"Claude Code requests approval for `{tool}` on `{target}`: {reason}",
        "tool": tool,
        "target": target,
        "reason": reason,
        "raw": event,
    }


def _approval_request_id(*, tool: str, target: str, reason: str) -> str:
    digest = hashlib.sha256(f"{tool}\0{target}\0{reason}".encode()).hexdigest()[:12]
    return f"approval_claude_code_{digest}"
