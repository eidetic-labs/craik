"""Support helpers for the Textual TUI runtime."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from craik.runtime.contract.command_result import CommandResult
from craik.runtime.providers.provider_transport import normalize_provider_family
from craik.runtime.shell.contract_runtime.mode_args import active_vendor_mode_spec
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmationRequest
from craik.runtime.shell.transcript_renderers import (
    render_claude_event,
    render_model_message,
    render_user_message,
)

# Per-vendor display labels for the status bar / cycle toast. Each vendor's REAL
# mode tokens map to short human labels; the high-risk bypass-equivalents
# (``bypassPermissions`` / ``yolo`` / ``danger-full-access``) keep a distinct
# "Bypass"-family treatment so the operator always sees the elevated posture.
CLAUDE_PERMISSION_MODE_LABELS = {
    "default": "Default",
    "acceptEdits": "Accept edits",
    "plan": "Plan",
    "dontAsk": "Don't ask",
    "bypassPermissions": "Bypass",
}
_VENDOR_MODE_LABELS: dict[str, dict[str, str]] = {
    "anthropic": CLAUDE_PERMISSION_MODE_LABELS,
    "google": {
        "default": "Default",
        "auto_edit": "Auto edit",
        "yolo": "Yolo",
        "plan": "Plan",
    },
    "openai": {
        "read-only": "Read-only",
        "workspace-write": "Workspace write",
        "danger-full-access": "Full access",
    },
}


class InterruptibleProcess(Protocol):
    def poll(self) -> int | None:
        raise NotImplementedError

    def terminate(self) -> None:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _ActivityDetails:
    tool: str | None = None
    target: str | None = None
    phase: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    files: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()


def _user_transcript_markup(text: str) -> object:
    return render_user_message(text)


def _model_transcript_markup(text: str, *, model_label: str = "Model") -> object:
    return render_model_message(text, model_label=model_label)


def _display_model_label(active_model: str | None) -> str:
    if not active_model:
        return "Model"
    if "/" not in active_model:
        return _title_model_id(active_model)
    provider, model = active_model.split("/", 1)
    provider_label = {
        "anthropic": "Anthropic",
        "claude": "Anthropic",
        "openai": "OpenAI",
        "google": "Google",
        "fixture": "Fixture",
    }.get(normalize_provider_family(provider), _title_model_id(provider))
    model_label = _title_model_id(model)
    if provider_label == "Google" and model_label.startswith("Gemini "):
        return f"Google {model_label}"
    return f"{provider_label} {model_label}"


def _title_model_id(model_id: str) -> str:
    cleaned = model_id.strip().replace("_", "-")
    if not cleaned:
        return "Model"
    parts = cleaned.split("-")
    if parts and _looks_like_date_suffix(parts[-1]):
        parts = parts[:-1]
    words: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part.isdigit():
            version = part
            if index + 1 < len(parts) and _is_minor_version_token(parts[index + 1]):
                version = f"{version}.{parts[index + 1]}"
                index += 1
            words.append(version)
        elif _is_minor_version_token(part) and words and words[-1].isdigit():
            words[-1] = f"{words[-1]}.{part}"
        else:
            words.append(_title_model_token(part))
        index += 1
    return " ".join(word for word in words if word).strip() or cleaned


def _looks_like_date_suffix(value: str) -> bool:
    return len(value) == 8 and value.isdigit() and value.startswith(("20", "19"))


def _is_minor_version_token(value: str) -> bool:
    return value.isdigit() and len(value) <= 2


def _title_model_token(value: str) -> str:
    lowered = value.lower()
    if lowered in {"gpt", "api", "cli"}:
        return lowered.upper()
    if lowered in {"llm", "vllm"}:
        return lowered.upper()
    return lowered.capitalize()


def _claude_progress_markup(text: str) -> object:
    return render_claude_event(text)


def _gateway_event_message(event: dict[str, object]) -> str | None:
    event_type = str(event.get("type") or "")
    data = event.get("data")
    if event_type == "prompt.submitted":
        preview = _data_string(data, "prompt_preview")
        return f"Gateway accepted prompt: {preview}" if preview else "Gateway accepted prompt."
    if event_type == "model.selected":
        label = _gateway_model_label(data)
        return f"Gateway selected {label}." if label else "Gateway selected model."
    if event_type == "run.working":
        phase = _data_string(data, "phase") or "thinking"
        return f"Gateway run is {phase}."
    if event_type == "run.started":
        run_id = event.get("run_id")
        if isinstance(run_id, str):
            return f"Gateway run started: `{run_id}`."
        return "Gateway run started."
    if event_type == "tool.used":
        tool = _data_string(data, "tool")
        target = _data_string(data, "target")
        command = _data_string(data, "command")
        if tool and target:
            return f"Claude Code used `{tool}` on `{target}`."
        if tool and command:
            return f"Claude Code used `{tool}`: `{command}`."
        return f"Claude Code used `{tool}`." if tool else "Claude Code used a tool."
    if event_type == "file.changed":
        target = _data_string(data, "target")
        return f"Claude Code changed `{target}`." if target else "Claude Code changed files."
    if event_type == "approval.requested":
        message = _data_string(data, "message")
        return message or "Claude Code requested approval."
    if event_type == "approval.denied":
        message = _data_string(data, "message")
        return message or "Claude Code approval denied."
    if event_type == "run.event":
        message = _data_string(data, "message")
        return message
    if event_type == "receipt.created":
        receipt_id = _data_string(data, "receipt_id")
        if receipt_id:
            return f"Gateway recorded receipt `{receipt_id}`."
        return "Gateway recorded receipt."
    if event_type == "run.output":
        summary = _data_string(data, "summary")
        return f"Gateway wrote output: {summary}" if summary else "Gateway wrote output."
    if event_type == "run.completed":
        status = _data_string(data, "status")
        return f"Gateway run completed: {status}." if status else "Gateway run completed."
    if event_type == "approval.resolved":
        decision = _data_string(data, "decision")
        return f"Gateway approval {decision}." if decision else "Gateway approval resolved."
    if event_type == "error":
        message = _data_string(data, "message")
        return f"Gateway error: {message}" if message else "Gateway error."
    return None


def _gateway_model_label(data: object) -> str | None:
    if not isinstance(data, dict):
        return None
    profile = data.get("profile")
    if isinstance(profile, dict):
        display_name = profile.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name
    model = data.get("model")
    provider_id = data.get("provider_id")
    if isinstance(provider_id, str) and isinstance(model, str):
        return _display_model_label(f"{provider_id}/{model}")
    if isinstance(model, str):
        return _display_model_label(model)
    backend = data.get("backend")
    return backend if isinstance(backend, str) and backend.strip() else None


def _data_string(data: object, key: str) -> str | None:
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _data_string_list(data: object, key: str) -> list[str]:
    if not isinstance(data, dict):
        return []
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _audited_run_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    outputs = payload.get("run_outputs")
    if not isinstance(outputs, list):
        return ""
    for output in outputs:
        if not isinstance(output, dict):
            continue
        observed = output.get("observed_output")
        if not isinstance(observed, dict):
            continue
        text = observed.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _latest_copyable_transcript_line(lines: list[str]) -> str:
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not _non_response_transcript_line(stripped):
            return stripped
    return ""


def _non_response_transcript_line(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith(">")
        or stripped.startswith("Queued input #")
        or stripped.startswith("Audited run:")
        or stripped.startswith("Claude Code:")
        or stripped.startswith("Transcript exported to ")
        or stripped in {"Audited run summary", "Transcript cleared. Receipts remain audited."}
    )


def _uses_model_backed_slash_execution(text: str) -> bool:
    try:
        arguments = shlex.split(text.strip())
    except ValueError:
        arguments = text.strip().split()
    if not arguments or arguments[0] != "/run":
        return False
    for index, argument in enumerate(arguments[1:], start=1):
        if argument == "--backend":
            return index + 1 < len(arguments) and arguments[index + 1] == "claude-code"
        if argument == "--backend=claude-code":
            return True
    return False


def _requires_claude_code_run_approval(
    text: str,
    *,
    env: dict[str, str] | None = None,
) -> bool:
    return _uses_model_backed_slash_execution(text)


def _is_claude_code_run_result(result: CommandResult) -> bool:
    return (
        result.command_name == "run"
        and isinstance(result.payload, dict)
        and result.payload.get("schema") == "craik.claude_code_run_execution"
    )


def _is_audited_run_payload(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("schema") in {
        "craik.provider_backed_run_execution",
        "craik.claude_code_run_execution",
    }


def _claude_code_run_approval_request(text: str, *, mode: str = "Default") -> ConfirmationRequest:
    posture = _claude_permission_mode_posture(mode)
    message = (
        "Approve this audited model run once?\n\n"
        f"Current mode: {mode} — {posture}\n\n"
        "- Read repository: .\n"
        "- Write documentation: docs/, README.md, CHANGELOG.md\n"
        "- Write Craik receipts and handoffs\n"
        "- Run verification commands\n\n"
        "Use Ctrl+C or /stop to interrupt the run after it starts."
    )
    return ConfirmationRequest(
        text,
        "Approve audited run authority?",
        message,
        confirm_label="Approve once",
        cancel_label="Deny",
        destructive=False,
    )


def _activity_details(message: str) -> _ActivityDetails:
    tool: str | None = None
    target: str | None = None
    phase = _activity_phase(message)
    task_id = _backticked_id(message, "task_")
    run_id = _backticked_id(message, "run_")
    files: list[str] = []
    commands: list[str] = []
    if "Claude Code is using `" in message:
        remainder = message.split("Claude Code is using `", 1)[1]
        tool = remainder.split("`", 1)[0]
    if " on `" in message:
        target = message.split(" on `", 1)[1].split("`", 1)[0]
    elif ": `" in message:
        target = message.split(": `", 1)[1].split("`", 1)[0]
    if target and _target_looks_like_file(target):
        files.append(target)
    if tool and tool.lower() == "bash" and target:
        commands.append(target)
        files.clear()
    for path in _diff_paths(message):
        if path not in files:
            files.append(path)
    if "permission denied" in message.lower() and ":" in message:
        parts = message.split(":", 2)
        if len(parts) >= 2:
            tool = parts[1].strip() or tool
    return _ActivityDetails(
        tool=tool,
        target=target,
        phase=phase,
        run_id=run_id,
        task_id=task_id,
        files=tuple(files),
        commands=tuple(commands),
    )


def _activity_phase(message: str) -> str | None:
    lowered = message.lower()
    if "preparing" in lowered:
        return "preparing"
    if "created task" in lowered:
        return "task"
    if "recorded" in lowered and "receipt" in lowered:
        return "receipts"
    if "building case file" in lowered:
        return "case file"
    if "compiling" in lowered:
        return "prompt"
    if "created run" in lowered or "process started" in lowered or "stream events" in lowered:
        return "running"
    if "using `" in lowered:
        return "tool"
    if "diff" in lowered:
        return "editing"
    if "returned a final result" in lowered or "completed" in lowered:
        return "finishing"
    if "permission denied" in lowered:
        return "blocked"
    if "interrupt" in lowered:
        return "interrupting"
    return None


def _backticked_id(message: str, prefix: str) -> str | None:
    match = re.search(rf"`({re.escape(prefix)}[^`]+)`", message)
    return match.group(1) if match else None


def _target_looks_like_file(target: str) -> bool:
    return "/" in target or "." in Path(target).name


def _diff_paths(message: str) -> tuple[str, ...]:
    paths: list[str] = []
    for match in re.finditer(r"^[+-]{3} [ab]/(.+)$", message, flags=re.MULTILINE):
        path = match.group(1).strip()
        if path and path not in paths:
            paths.append(path)
    return tuple(paths)


def _vendor_mode_display(family: str, mode: str) -> str:
    labels = _VENDOR_MODE_LABELS.get(family, CLAUDE_PERMISSION_MODE_LABELS)
    return labels.get(mode, mode)


def _claude_permission_mode_label(env: dict[str, str]) -> str | None:
    """Return the ACTIVE vendor's permission-mode label for the status bar.

    Vendor-aware: resolves the active vendor (anthropic / google / openai) and
    renders its CURRENT stored mode with that vendor's label prefix (``Claude`` /
    ``Gemini`` / ``Codex``), e.g. ``"Claude Accept edits"`` or ``"Gemini Yolo"``.
    Returns ``None`` when the active vendor is at its default (no mode chip).
    """
    spec = active_vendor_mode_spec(env)
    stored = env.get(spec.env_var)
    if stored is None or stored == spec._default_stored():
        return None
    return f"{spec.label} {_vendor_mode_display(spec.family, stored)}"


def _active_permission_mode_display(env: dict[str, str]) -> str:
    """Return the active vendor's CURRENT mode as a bare display label.

    Unlike ``_claude_permission_mode_label`` (vendor-prefixed, status-bar
    facing), this returns just the mode label (e.g. ``"Plan"`` / ``"Default"``)
    for the approval-request copy whose posture text keys off the bare label.
    """
    spec = active_vendor_mode_spec(env)
    stored = env.get(spec.env_var, spec._default_stored())
    return _vendor_mode_display(spec.family, stored)


def _active_permission_mode_label_bare(env: dict[str, str]) -> str | None:
    """Bare active-vendor mode label, or ``None`` when at the vendor default.

    Feeds the run-activity panel (which renders its own posture line and skips
    the chip entirely at default).
    """
    spec = active_vendor_mode_spec(env)
    stored = env.get(spec.env_var)
    if stored is None or stored == spec._default_stored():
        return None
    return _vendor_mode_display(spec.family, stored)


def _claude_permission_mode_posture(mode: str) -> str:
    normalized = mode.lower()
    if normalized == "plan":
        return "the backend should preview intent without editing."
    if normalized in {"accept edits", "auto edit"}:
        return "file edits can proceed with fewer prompts."
    if normalized in {"dontask", "don't ask"}:
        return "tools run without prompting; craik records each."
    # The high-risk bypass-equivalents across vendors: bypassPermissions
    # (Claude), yolo (Gemini), full access / danger-full-access (Codex).
    if normalized in {"bypasspermissions", "bypass", "yolo", "full access", "danger-full-access"}:
        return "permission gates are bypassed; craik observes and records every tool call."
    if normalized in {"read-only", "workspace write", "workspace-write"}:
        return "the backend follows its sandbox boundary; craik records every tool call."
    return "the backend follows its normal tool permission gates."
