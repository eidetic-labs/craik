"""Claude Code stream parsing and provenance helpers."""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path


def _claude_stream_line_events(line: str) -> tuple[list[dict[str, object]], str | None]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        text = _safe_cli_detail(line)
        return ([{"kind": "output", "message": text, "text": line}], line)
    if not isinstance(event, dict):
        return [], None
    event_type = str(event.get("type") or "")
    subtype = str(event.get("subtype") or "")
    if event_type == "result":
        denial_events = _permission_denial_events(event)
        text = _claude_result_text(event)
        if denial_events:
            if text:
                return (
                    [
                        *denial_events,
                        _hidden_status_event(
                            kind="result",
                            message="Claude Code returned a final result.",
                        ),
                    ],
                    text,
                )
            return denial_events, None
        if text:
            return (
                [
                    _hidden_status_event(
                        kind="result",
                        message="Claude Code returned a final result.",
                    )
                ],
                text,
            )
        if event.get("is_error"):
            detail = _safe_cli_detail(json.dumps(event, sort_keys=True))
            return ([{"kind": "error", "message": detail}], None)
        return (
            [_hidden_status_event(kind="result", message="Claude Code completed.")],
            None,
        )
    if event_type == "assistant":
        events = _assistant_progress_events(event)
        final_text = "\n".join(
            str(item.get("text"))
            for item in events
            if item.get("kind") == "assistant_text" and item.get("text")
        ).strip()
        return events, final_text or None
    if _is_approval_request_event(event):
        approval = _approval_request_event(event)
        return ([approval], None)
    if event_type == "system":
        if subtype:
            return (
                [
                    {
                        "kind": "system",
                        "message": f"Claude Code system event: {subtype}.",
                        "subtype": subtype,
                    }
                ],
                None,
            )
        return [], None
    if event_type:
        return (
            [
                _hidden_status_event(
                    kind="event",
                    message=f"Claude Code event: {event_type}.",
                )
            ],
            None,
        )
    return [], None


def _hidden_status_event(*, kind: str, message: str) -> dict[str, object]:
    return {
        "kind": kind,
        "message": message,
        "transcript_visibility": "hidden",
    }


def _claude_result_text(event: dict[str, object]) -> str:
    for key in ("result", "text", "content", "summary", "message"):
        text = _extract_text_payload(event.get(key))
        if text:
            return text
    return ""


def _extract_text_payload(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_extract_text_payload(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if not isinstance(value, dict):
        return ""
    if value.get("type") == "text" and isinstance(value.get("text"), str):
        return str(value["text"]).strip()
    content = value.get("content")
    if content is not None:
        text = _extract_text_payload(content)
        if text:
            return text
    for key in ("text", "result", "summary", "message"):
        text = _extract_text_payload(value.get(key))
        if text:
            return text
    return ""


def _claude_completion_fallback(
    *,
    progress_events: list[str],
    structured_events: list[dict[str, object]],
    raw_events: list[str],
) -> str:
    activity = _claude_activity_summary(structured_events)
    lines = [
        "Claude Code completed, but the CLI stream did not include a final response body."
    ]
    tools = _string_list(activity.get("tools"))
    files = _string_list(activity.get("files"))
    commands = _string_list(activity.get("commands"))
    if tools or files or commands:
        lines.append("")
        lines.append("Observed activity:")
        if tools:
            lines.append(f"- Tools: {', '.join(tools)}")
        if files:
            lines.append(f"- Files: {', '.join(files)}")
        if commands:
            lines.append("- Commands:")
            lines.extend(f"  - {command}" for command in commands)
    if progress_events:
        lines.append("")
        lines.append("Last event:")
        lines.append(f"- {progress_events[-1]}")
    if raw_events and not progress_events:
        lines.append("")
        lines.append(f"Raw stream events captured: {len(raw_events)}")
    return "\n".join(lines)


def _assistant_progress_events(event: dict[str, object]) -> list[dict[str, object]]:
    message = event.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        text = _safe_cli_detail(content)
        return [{"kind": "assistant_text", "message": text, "text": content}]
    if not isinstance(content, list):
        return []
    events: list[dict[str, object]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text" and item.get("text"):
            text = str(item["text"])
            events.append(
                {
                    "kind": "assistant_text",
                    "message": _safe_cli_detail(text),
                    "text": text,
                }
            )
        elif item_type == "tool_use":
            name = str(item.get("name") or "tool")
            summary, details = _tool_use_details(name, item.get("input"))
            events.append({"kind": "tool_use", "message": summary, **details})
            change_event = _tool_use_file_change_event(name, item.get("input"), details)
            if change_event is not None:
                events.append(change_event)
        elif item_type == "tool_result":
            events.append(_tool_result_event(item))
    return events


def _assistant_event_text(event: dict[str, object]) -> str | None:
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return _safe_cli_detail(content)
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text" and item.get("text"):
            parts.append(_safe_cli_detail(str(item["text"])))
        elif item_type == "tool_use":
            name = str(item.get("name") or "tool")
            parts.append(_tool_use_summary(name, item.get("input")))
        elif item_type == "tool_result":
            parts.append(_tool_result_summary(item))
    return " ".join(parts).strip() or None


def _tool_use_summary(name: str, raw_input: object) -> str:
    summary, _details = _tool_use_details(name, raw_input)
    return summary


def _tool_use_details(name: str, raw_input: object) -> tuple[str, dict[str, object]]:
    details: dict[str, object] = {"tool": name}
    if not isinstance(raw_input, dict):
        return f"Claude Code is using `{name}`.", details
    for key in ("file_path", "path", "notebook_path"):
        value = raw_input.get(key)
        if value:
            details["target"] = str(value)
            details["files"] = [str(value)]
            return f"Claude Code is using `{name}` on `{value}`.", details
    command = raw_input.get("command")
    if command:
        details["command"] = str(command)
        return f"Claude Code is using `{name}`: `{_safe_cli_detail(str(command))}`.", details
    return f"Claude Code is using `{name}`.", details


def _tool_use_file_change_event(
    name: str,
    raw_input: object,
    details: dict[str, object],
) -> dict[str, object] | None:
    if not isinstance(raw_input, dict):
        return None
    lowered = name.lower()
    path = _tool_input_path(raw_input)
    diff_text = ""
    if lowered == "edit":
        diff_text = _edit_input_diff(path, raw_input)
    elif lowered == "multiedit":
        diff_text = _multi_edit_input_diff(path, raw_input)
    elif lowered == "write":
        diff_text = _write_input_diff(path, raw_input)
    if not diff_text:
        return None
    files = [path] if path else []
    return {
        **{key: value for key, value in details.items() if key not in {"message"}},
        "kind": "file_change",
        "tool": name,
        "target": path,
        "files": files,
        "language": "diff",
        "text": diff_text,
        "message": "Claude Code diff:\n" + _clip_block(diff_text),
    }


def _tool_input_path(raw_input: dict[str, object]) -> str:
    for key in ("file_path", "path", "notebook_path"):
        value = raw_input.get(key)
        if value:
            return str(value)
    return "unknown"


def _edit_input_diff(path: str, raw_input: dict[str, object]) -> str:
    old = raw_input.get("old_string")
    new = raw_input.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str):
        return ""
    return _unified_diff(path, old, new)


def _multi_edit_input_diff(path: str, raw_input: dict[str, object]) -> str:
    edits = raw_input.get("edits")
    if not isinstance(edits, list):
        return ""
    diffs: list[str] = []
    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            continue
        old = edit.get("old_string")
        new = edit.get("new_string")
        if isinstance(old, str) and isinstance(new, str):
            diffs.append(_unified_diff(f"{path} edit {index}", old, new))
    return "\n".join(diff for diff in diffs if diff)


def _write_input_diff(path: str, raw_input: dict[str, object]) -> str:
    content = raw_input.get("content")
    if not isinstance(content, str):
        return ""
    return _unified_diff(path, "", content)


def _unified_diff(path: str, before: str, after: str) -> str:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(line.rstrip("\n") for line in diff)


def _tool_result_summary(item: dict[str, object]) -> str:
    return str(_tool_result_event(item)["message"])


def _tool_result_event(item: dict[str, object]) -> dict[str, object]:
    if item.get("is_error") is True:
        return {"kind": "tool_result", "message": "Claude Code tool result: error.", "error": True}
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        details: dict[str, object] = {"kind": "tool_result", "text": content}
        if _looks_like_diff(content):
            details["language"] = "diff"
            details["message"] = "Claude Code diff:\n" + _clip_block(content)
        elif _looks_like_code(content):
            details["language"] = "text"
            details["message"] = "Claude Code code/output:\n" + _clip_block(content)
        else:
            details["message"] = f"Claude Code tool result: {_safe_cli_detail(content)}"
        return details
    return {"kind": "tool_result", "message": "Claude Code received a tool result."}


def _permission_denial_events(event: dict[str, object]) -> list[dict[str, object]]:
    denials = event.get("permission_denials")
    if not isinstance(denials, list) or not denials:
        return []
    events: list[dict[str, object]] = []
    for denial in denials:
        if isinstance(denial, dict):
            name = denial.get("tool_name") or denial.get("name") or denial.get("tool")
            reason = denial.get("reason") or denial.get("message") or denial.get("description")
            message = "Claude Code permission denied"
            if name and reason:
                message = f"Claude Code permission denied: {name}: {reason}"
            elif name:
                message = f"Claude Code permission denied: {name}"
            elif reason:
                message = f"Claude Code permission denied: {reason}"
            events.append(
                {
                    "kind": "permission_denial",
                    "message": _safe_cli_detail(message),
                    "transcript_visibility": "approval",
                    "tool": str(name) if name else None,
                    "reason": str(reason) if reason else None,
                }
            )
        else:
            events.append(
                {
                    "kind": "permission_denial",
                    "message": f"Claude Code permission denied: {_safe_cli_detail(str(denial))}",
                    "transcript_visibility": "approval",
                    "reason": str(denial),
                }
            )
    return events


def _permission_denial_text(event: dict[str, object]) -> str | None:
    denials = event.get("permission_denials")
    if not isinstance(denials, list) or not denials:
        return None
    summaries: list[str] = []
    for denial in denials:
        if isinstance(denial, dict):
            name = denial.get("tool_name") or denial.get("name") or denial.get("tool")
            reason = denial.get("reason") or denial.get("message") or denial.get("description")
            if name and reason:
                summaries.append(f"{name}: {reason}")
            elif name:
                summaries.append(str(name))
            elif reason:
                summaries.append(str(reason))
        else:
            summaries.append(str(denial))
    return "Claude Code permission denied: " + "; ".join(
        _safe_cli_detail(item) for item in summaries
    )


def _is_approval_request_event(event: dict[str, object]) -> bool:
    event_type = str(event.get("type") or "").lower()
    subtype = str(event.get("subtype") or "").lower()
    if "approval" in event_type or "permission_request" in event_type:
        return True
    return "approval" in subtype or "permission_request" in subtype


def _approval_request_event(event: dict[str, object]) -> dict[str, object]:
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


def _looks_like_diff(text: str) -> bool:
    lines = text.splitlines()
    return any(line.startswith(("diff --git", "@@ ", "+++ ", "--- ")) for line in lines) or any(
        line.startswith("+") for line in lines
    ) and any(line.startswith("-") for line in lines)


def _looks_like_code(text: str) -> bool:
    markers = ("def ", "class ", "import ", "from ", "function ", "const ", "let ", "{", "}")
    return any(marker in text for marker in markers)


def _claude_activity_summary(events: list[dict[str, object]]) -> dict[str, object]:
    files: list[str] = []
    commands: list[str] = []
    denials: list[dict[str, object]] = []
    approvals: list[dict[str, object]] = []
    tools: list[str] = []
    for event in events:
        tool = event.get("tool")
        if isinstance(tool, str) and tool and tool not in tools:
            tools.append(tool)
        command = event.get("command")
        if isinstance(command, str) and command and command not in commands:
            commands.append(command)
        raw_files = event.get("files")
        for path in raw_files if isinstance(raw_files, list) else []:
            if isinstance(path, str) and path not in files:
                files.append(path)
        target = event.get("target")
        if isinstance(target, str) and _target_looks_like_file(target) and target not in files:
            files.append(target)
        if event.get("kind") == "permission_denial":
            denials.append(
                {
                    "tool": event.get("tool"),
                    "reason": event.get("reason"),
                    "message": event.get("message"),
                }
            )
        if event.get("kind") in {"approval_request", "approval_decision"}:
            approvals.append(event)
    return {
        "tools": tools,
        "files": files,
        "commands": commands,
        "permission_denials": denials,
        "runtime_approvals": approvals,
    }


def _target_looks_like_file(target: str) -> bool:
    return "/" in target or "." in Path(target).name


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _safe_cli_detail(output: str) -> str:
    return " ".join(output.split())[:300]



def _clip_block(output: str, *, limit: int = 2000) -> str:
    if len(output) <= limit:
        return output
    return output[: limit - 1].rstrip() + "\n..."



def _clip_summary(text: str, *, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized or "Claude Code completed without output."
    return normalized[: limit - 1].rstrip() + "..."
