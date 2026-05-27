"""Claude Code Gateway backend execution and provenance capture."""

from __future__ import annotations

import difflib
import json
import os
import queue
import re
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Literal, Protocol, cast

from craik.contracts.models import (
    CapabilityGrant,
    CapabilityReceipt,
    CapabilityTarget,
    ProjectProfile,
    ReceiptResult,
    RunOutput,
    ToolResultAttestation,
)
from craik.runtime.auth.profile import CredentialKind
from craik.runtime.auth.store import AuthProfileStore, AuthProfileStoreError
from craik.runtime.modeling import ModelSettingsStore
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.projects.prompts import PromptCompiler
from craik.runtime.sandbox.local_process_backend import (
    LocalProcessStartError,
    LocalProcessTimeoutExpired,
    start_reviewed_local_process,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.handoffs import HandoffWriter
from craik.runtime.work.runs import RunTransition, TaskRunManager
from craik.runtime.work.tasks import create_task

__all__ = [
    "CLAUDE_CODE_RUN_APPROVED_ENV",
    "CLAUDE_PERMISSION_MODE_ENV",
    "ClaudeCodeExecution",
    "ClaudeCodeInterrupted",
    "anthropic_uses_claude_cli_marker",
    "claude_code_progress",
    "execute_claude_code_run",
]

_CLAUDE_CODE_PROGRESS: ContextVar[Callable[[str], None] | None] = ContextVar(
    "claude_code_progress",
    default=None,
)
_CLAUDE_CODE_EVENT: ContextVar[Callable[[dict[str, object]], None] | None] = ContextVar(
    "claude_code_event",
    default=None,
)
class _ClaudeProcess(Protocol):
    stdout: IO[str] | None
    returncode: int | None
    pid: int

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


_CLAUDE_CODE_PROCESS: ContextVar[Callable[[_ClaudeProcess | None], None] | None] = (
    ContextVar(
        "claude_code_process",
        default=None,
    )
)
_CLAUDE_CODE_CANCEL: ContextVar[threading.Event | None] = ContextVar(
    "claude_code_cancel",
    default=None,
)
CLAUDE_CODE_RUN_APPROVED_ENV = "CRAIK_CLAUDE_CODE_RUN_APPROVED"
CLAUDE_PERMISSION_MODE_ENV = "CRAIK_CLAUDE_PERMISSION_MODE"


@dataclass(frozen=True)
class ClaudeCodeExecution:
    """Captured Claude Code stream output."""

    text: str
    raw_events: list[str]
    progress_events: list[str]
    structured_events: list[dict[str, object]]


class ClaudeCodeInterrupted(RuntimeError):
    """Raised when the operator interrupts a Claude Code run."""


@contextmanager
def claude_code_progress(
    callback: Callable[[str], None] | None,
    *,
    event_callback: Callable[[dict[str, object]], None] | None = None,
    process_callback: Callable[[_ClaudeProcess | None], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Iterator[None]:
    """Install per-dispatch Claude Code progress and cancellation hooks."""
    progress_token = _CLAUDE_CODE_PROGRESS.set(callback)
    event_token = _CLAUDE_CODE_EVENT.set(event_callback)
    process_token = _CLAUDE_CODE_PROCESS.set(process_callback)
    cancel_token = _CLAUDE_CODE_CANCEL.set(cancel_event)
    try:
        yield
    finally:
        _CLAUDE_CODE_CANCEL.reset(cancel_token)
        _CLAUDE_CODE_PROCESS.reset(process_token)
        _CLAUDE_CODE_EVENT.reset(event_token)
        _CLAUDE_CODE_PROGRESS.reset(progress_token)


def execute_claude_code_run(
    prompt: str,
    env: dict[str, str] | None,
    *,
    require_operator_approval: bool = True,
) -> dict[str, object]:
    store = LocalStore.from_env(env)
    try:
        _emit_claude_code_progress("Preparing audited Claude Code run.")
        store.initialize()
        project = _project_for_cwd(store)
        if require_operator_approval:
            _require_claude_code_run_approval(env)
        title = _title_from_prompt(prompt)
        task = create_task(
            store,
            title=title,
            objective=prompt,
            project_id=project.id,
            requested_by="user:tui",
            mode="implement",
            expected_outputs=["runner_step_result", "handoff"],
        )
        _emit_claude_code_progress(f"Created task `{task.id}`.")
        grant_ids = _put_claude_code_grants(store, task.id)
        approval_receipt = _put_claude_code_approval_receipt(
            store,
            task.id,
            grant_ids,
            operator_approved=require_operator_approval,
        )
        _emit_claude_code_progress("Recorded Claude Code authority grants and receipt.")
        _emit_claude_code_progress("Building case file.")
        case_file = CaseFileAssembler(store).build(task.id)
        _emit_claude_code_progress("Compiling Claude Code prompt.")
        compiled = PromptCompiler(store).compile(
            task.id,
            runner_id="claude-code",
            expected_output_schemas=["craik.runner_step_result", "craik.handoff"],
        )
        run = TaskRunManager(store).create(
            task_id=task.id,
            case_file_id=case_file.id,
            policy_envelope_id=compiled.policy_envelope_id,
            runner_id="claude-code",
            runner_mode="live",
            runner_metadata=[
                {
                    "runner_id": "claude-code",
                    "backend": "claude-code",
                    "execution_mode": "local-cli",
                    "operator_approved_grants": require_operator_approval,
                    "grant_ids": grant_ids,
                }
            ],
            receipt_ids=[approval_receipt.id],
        )
        _emit_claude_code_progress(f"Created run `{run.id}`.")
        run_manager = TaskRunManager(store)
        run_manager.transition(
            run.id,
            RunTransition(status="running", phase="act", iteration=1, last_step_key="claude_code"),
        )
        status: Literal["completed", "failed", "interrupted"] = "completed"
        stop_reason = "Claude Code completed."
        try:
            execution = _execute_claude_code_prompt(
                _claude_code_execution_prompt(compiled.prompt, prompt),
                env=env,
            )
            claude_output = execution.text
            receipt_status: Literal["passed", "failed", "skipped"] = "passed"
            diagnostics: list[str] = []
        except ClaudeCodeInterrupted as error:
            claude_output = str(error)
            execution = ClaudeCodeExecution(
                text=claude_output,
                raw_events=[],
                progress_events=[],
                structured_events=[],
            )
            status = "interrupted"
            stop_reason = str(error)
            receipt_status = "skipped"
            diagnostics = [str(error)]
        except RuntimeError as error:
            claude_output = str(error)
            execution = ClaudeCodeExecution(
                text=claude_output,
                raw_events=[],
                progress_events=[],
                structured_events=[],
            )
            status = "failed"
            stop_reason = str(error)
            receipt_status = "failed"
            diagnostics = [str(error)]
        receipt = store.put_receipt(
            CapabilityReceipt(
                id=f"receipt_{run.id}_claude_code",
                task_id=task.id,
                actor="runner:claude-code",
                capability="claude_code.execute",
                target=str(Path.cwd()),
                policy_profile="trusted-local",
                reason="Execute a TUI audited run through the local Claude Code CLI.",
                result=ReceiptResult(
                    status=receipt_status,
                    summary=_clip_summary(claude_output),
                    metadata={
                        "backend": "claude-code",
                        "active_model": _active_model(env),
                        "permission_mode": _claude_permission_mode(env),
                        "command": _claude_code_command_summary(env),
                        "operator_approved_grants": require_operator_approval,
                        "default_attested_backend": not require_operator_approval,
                        "grant_ids": grant_ids,
                        "approval_receipt_id": approval_receipt.id,
                    },
                ),
                created_at=datetime.now(UTC),
            )
        )
        activity = _claude_activity_summary(execution.structured_events)
        attestations = _put_claude_code_tool_attestations(
            store,
            task_id=task.id,
            run_id=run.id,
            case_file_id=case_file.id,
            receipt_id=receipt.id,
            events=execution.structured_events,
        )
        output = RunOutput(
            id=f"runout_{run.id.removeprefix('run_')}_claude_code",
            run_id=run.id,
            step_result_id=f"runner_step_result_{run.id}_claude_code",
            task_id=task.id,
            phase="act",
            summary=_clip_summary(claude_output),
            observed_output={
                "backend": "claude-code",
                "command": _claude_code_command_summary(env),
                "text": claude_output,
                "model": _active_model(env),
                "raw_stream_events": execution.raw_events,
                "progress_events": execution.progress_events,
                "structured_events": execution.structured_events,
                "activity": activity,
            },
            diagnostics=diagnostics,
            receipt_ids=[approval_receipt.id, receipt.id],
            artifacts=[compiled.id, *[attestation.id for attestation in attestations]],
            created_at=datetime.now(UTC),
        )
        store.put_run_output(output)
        final_run = run_manager.transition(
            run.id,
            RunTransition(
                status=status,
                phase="stop",
                receipt_id=receipt.id,
                stop_reason=stop_reason,
                completed_step_key="claude_code" if status == "completed" else None,
            ),
        )
        handoff = HandoffWriter(store).create_from_run(
            final_run.id,
            agent="runner:claude-code",
            commands_run=[_claude_code_command_summary(env)],
            tests_run=["Claude Code backend executed from the TUI"],
        )
        final_run = store.get_task_run(final_run.id) or final_run
        return {
            "schema": "craik.claude_code_run_execution",
            "version": "0.1.0",
            "status": final_run.status,
            "project": project.model_dump(mode="json", by_alias=True),
            "task": task.model_dump(mode="json", by_alias=True),
            "run": final_run.model_dump(mode="json", by_alias=True),
            "handoff": handoff.model_dump(mode="json", by_alias=True),
            "compiled_prompt": compiled.model_dump(mode="json", by_alias=True),
            "run_outputs": [output.model_dump(mode="json", by_alias=True)],
            "receipt_ids": [approval_receipt.id, receipt.id],
            "backend": "claude-code",
            "next_commands": [
                f"/run inspect {final_run.id}",
                "/handoffs",
                "/receipts list",
            ],
        }
    finally:
        store.close()


def _require_claude_code_run_approval(env: dict[str, str] | None) -> None:
    values = env or {}
    if values.get(CLAUDE_CODE_RUN_APPROVED_ENV) == "1":
        return
    raise ValueError(
        "Claude Code run requires operator approval for repo.write.docs, "
        "receipt.write, and shell.test. Use the TUI or set "
        f"`{CLAUDE_CODE_RUN_APPROVED_ENV}=1` for a deliberate non-interactive run."
    )


def _put_claude_code_grants(store: LocalStore, task_id: str) -> list[str]:
    grants = [
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_repo_read",
            task_id=task_id,
            capability="repo.read",
            target=CapabilityTarget(paths=["."]),
            operations=["read"],
            reason="Allow Claude Code to inspect the current repository for the audited run.",
            approved_by="user:tui",
        ),
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_repo_write_docs",
            task_id=task_id,
            capability="repo.write.docs",
            target=CapabilityTarget(paths=["docs", "README.md", "CHANGELOG.md"]),
            operations=["read", "write"],
            reason="Allow Claude Code to update documentation for the audited run.",
            approved_by="user:tui",
        ),
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_receipt_write",
            task_id=task_id,
            capability="receipt.write",
            target=CapabilityTarget(paths=["craik-runtime"]),
            operations=["write"],
            reason="Allow Craik to persist receipts for the delegated Claude Code run.",
            approved_by="user:tui",
        ),
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_shell_verify",
            task_id=task_id,
            capability="shell.test",
            target=CapabilityTarget(paths=["."]),
            operations=["execute"],
            reason="Allow Claude Code to run verification commands for documentation changes.",
            approved_by="user:tui",
        ),
    ]
    for grant in grants:
        store.put_capability_grant(grant)
    return [grant.id for grant in grants]


def _put_claude_code_approval_receipt(
    store: LocalStore,
    task_id: str,
    grant_ids: list[str],
    *,
    operator_approved: bool = True,
) -> CapabilityReceipt:
    actor = "user:tui" if operator_approved else "system:craik"
    capability = "approval.decide" if operator_approved else "authority.delegate"
    reason = (
        "Operator approved Claude Code repository, receipt, and verification grants."
        if operator_approved
        else "Craik selected Claude Code as the default attested backend for Anthropic marker auth."
    )
    summary = (
        "Operator approved Claude Code run authority for this task."
        if operator_approved
        else "Craik delegated the task to Claude Code to capture stream provenance."
    )
    return store.put_receipt(
        CapabilityReceipt(
            id=f"receipt_{task_id.removeprefix('task_')}_claude_code_approval",
            task_id=task_id,
            actor=actor,
            capability=capability,
            target="claude-code-run-grants",
            policy_profile="trusted-local",
            reason=reason,
            result=ReceiptResult(
                status="passed",
                summary=summary,
                metadata={
                    "backend": "claude-code",
                    "approved": operator_approved,
                    "default_attested_backend": not operator_approved,
                    "grant_ids": grant_ids,
                    "capabilities": [
                        "repo.read",
                        "repo.write.docs",
                        "receipt.write",
                        "shell.test",
                    ],
                },
            ),
            created_at=datetime.now(UTC),
        )
    )


def _execute_claude_code_prompt(
    prompt: str,
    *,
    env: dict[str, str] | None,
) -> ClaudeCodeExecution:
    executable = shutil.which("claude")
    if executable is None:
        raise RuntimeError("Claude CLI was not found; install Claude Code and run `claude`")
    command = [
        executable,
        "--tools",
        "default",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    model_arg = _claude_model_arg(_active_model(env))
    if model_arg:
        command.extend(["--model", model_arg])
    permission_mode = _claude_permission_mode(env)
    if permission_mode:
        command.extend(["--permission-mode", permission_mode])
    command.extend(["-p", prompt.strip()])
    _emit_claude_code_progress(f"Starting `{_claude_code_command_summary(env)}`")
    try:
        process = start_reviewed_local_process(
            command,
            stdout="pipe",
            stderr="stdout",
            env=_claude_code_env(env),
        )
    except (OSError, LocalProcessStartError) as exc:
        raise RuntimeError("Claude Code could not be executed") from exc

    _set_claude_code_process(process)
    pid = getattr(process, "pid", "unknown")
    _emit_claude_code_progress(f"Claude Code process started (pid {pid}).")
    _emit_claude_code_progress("Waiting for Claude Code stream events.")
    cancel_event = _CLAUDE_CODE_CANCEL.get()
    try:
        if cancel_event is not None and cancel_event.is_set():
            _terminate_claude_code_process(process)
        output_parts: list[str] = []
        raw_events: list[str] = []
        progress_events: list[str] = []
        structured_events: list[dict[str, object]] = []
        if process.stdout is not None:
            line_queue: queue.Queue[str | None] = queue.Queue()
            reader = threading.Thread(
                target=_read_claude_code_stdout,
                args=(process.stdout, line_queue),
                name="craik-claude-code-stdout",
                daemon=True,
            )
            reader.start()
            last_heartbeat = time.monotonic()
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    _terminate_claude_code_process(process)
                    break
                try:
                    raw_line = line_queue.get(timeout=1.0)
                except queue.Empty:
                    if process.poll() is not None and line_queue.empty():
                        break
                    now = time.monotonic()
                    if now - last_heartbeat >= 10:
                        _emit_claude_code_progress(
                            "Claude Code is still running; waiting for stream output."
                        )
                        last_heartbeat = now
                    continue
                if raw_line is None:
                    break
                line = raw_line.strip()
                if not line:
                    continue
                raw_events.append(line)
                parsed_events, final_text = _claude_stream_line_events(line)
                structured_events.extend(parsed_events)
                for event in parsed_events:
                    _emit_claude_code_event(event)
                    event_text = str(event.get("message") or "").strip()
                    if not event_text:
                        continue
                    progress_events.append(event_text)
                    _emit_claude_code_progress(event_text)
                if final_text:
                    output_parts.append(final_text)
        try:
            return_code = process.wait(timeout=30)
        except LocalProcessTimeoutExpired as exc:
            process.kill()
            raise RuntimeError("Claude Code prompt did not exit after stream ended") from exc
    finally:
        _set_claude_code_process(None)
    output = "\n".join(part for part in output_parts if part.strip()).strip()
    if cancel_event is not None and cancel_event.is_set():
        raise ClaudeCodeInterrupted("Claude Code run interrupted by operator.")
    if return_code != 0:
        detail = _safe_cli_detail(output)
        raise RuntimeError("Claude Code prompt failed" + (f": {detail}" if detail else ""))
    if output:
        return ClaudeCodeExecution(
            text=output,
            raw_events=raw_events,
            progress_events=progress_events,
            structured_events=structured_events,
        )
    fallback_output = _claude_completion_fallback(
        progress_events=progress_events,
        structured_events=structured_events,
        raw_events=raw_events,
    )
    return ClaudeCodeExecution(
        text=fallback_output,
        raw_events=raw_events,
        progress_events=progress_events,
        structured_events=structured_events,
    )


def _emit_claude_code_progress(message: str) -> None:
    callback = _CLAUDE_CODE_PROGRESS.get()
    if callback is not None and message.strip():
        callback(message.strip())


def _emit_claude_code_event(event: dict[str, object]) -> None:
    callback = _CLAUDE_CODE_EVENT.get()
    if callback is not None:
        callback(dict(event))


def _set_claude_code_process(process: _ClaudeProcess | None) -> None:
    callback = _CLAUDE_CODE_PROCESS.get()
    if callback is not None:
        callback(process)


def _terminate_claude_code_process(process: _ClaudeProcess) -> None:
    if process.poll() is not None:
        return
    process.terminate()


def _read_claude_code_stdout(
    stream: object,
    line_queue: queue.Queue[str | None],
) -> None:
    try:
        for raw_line in cast(Iterator[object], stream):
            line_queue.put(str(raw_line))
    finally:
        line_queue.put(None)


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
                        {"kind": "result", "message": "Claude Code returned a final result."},
                    ],
                    text,
                )
            return denial_events, None
        if text:
            return ([{"kind": "result", "message": "Claude Code returned a final result."}], text)
        if event.get("is_error"):
            detail = _safe_cli_detail(json.dumps(event, sort_keys=True))
            return ([{"kind": "error", "message": detail}], None)
        return ([{"kind": "result", "message": "Claude Code completed."}], None)
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
        return ([{"kind": "event", "message": f"Claude Code event: {event_type}."}], None)
    return [], None


def _claude_stream_line_text(line: str) -> tuple[str | None, str | None]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return _safe_cli_detail(line), line
    if not isinstance(event, dict):
        return None, None
    event_type = str(event.get("type") or "")
    subtype = str(event.get("subtype") or "")
    if event_type == "result":
        permission_denials = _permission_denial_text(event)
        if permission_denials:
            return permission_denials, None
        result_text = _claude_result_text(event)
        if result_text:
            return "Claude Code returned a final result.", result_text
        if event.get("is_error"):
            return _safe_cli_detail(json.dumps(event, sort_keys=True)), None
        return "Claude Code completed.", None
    if event_type == "assistant":
        assistant_text = _assistant_event_text(event)
        return assistant_text, assistant_text
    if event_type == "system":
        if subtype:
            return f"Claude Code system event: {subtype}.", None
        return None, None
    if event_type:
        return f"Claude Code event: {event_type}.", None
    return None, None


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
                    "tool": str(name) if name else None,
                    "reason": str(reason) if reason else None,
                }
            )
        else:
            events.append(
                {
                    "kind": "permission_denial",
                    "message": f"Claude Code permission denied: {_safe_cli_detail(str(denial))}",
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
        "message": f"Claude Code requests approval for `{tool}` on `{target}`: {reason}",
        "tool": tool,
        "target": target,
        "reason": reason,
        "raw": event,
    }


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


def _put_claude_code_tool_attestations(
    store: LocalStore,
    *,
    task_id: str,
    run_id: str,
    case_file_id: str,
    receipt_id: str,
    events: list[dict[str, object]],
) -> list[ToolResultAttestation]:
    attestations: list[ToolResultAttestation] = []
    for index, event in enumerate(events, start=1):
        if event.get("kind") != "tool_use":
            continue
        tool = event.get("tool")
        if not isinstance(tool, str) or not tool:
            continue
        attestation = ToolResultAttestation(
            id=(
                f"attestation_{task_id.removeprefix('task_')}_"
                f"{run_id.removeprefix('run_')}_{index}_{_attestation_slug(tool)}"
            ),
            task_id=task_id,
            case_file_id=case_file_id,
            tool_name=f"claude_code.{tool}",
            tool_identity=str(event.get("target") or event.get("command") or tool),
            command=_claude_tool_command(event),
            observed_output_summary=str(
                event.get("message") or f"Claude Code used {tool}."
            ),
            trust_class="observed",
            status="attested",
            receipt_id=receipt_id,
            captured_at=datetime.now(UTC),
        )
        store.put_tool_result_attestation(attestation)
        attestations.append(attestation)
    return attestations


def _claude_tool_command(event: dict[str, object]) -> str | None:
    command = event.get("command")
    if isinstance(command, str) and command:
        return command
    target = event.get("target")
    if isinstance(target, str) and target:
        return target
    return None


def _attestation_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower() or "tool"


def _target_looks_like_file(target: str) -> bool:
    return "/" in target or "." in Path(target).name


def _claude_code_execution_prompt(compiled_prompt: str, objective: str) -> str:
    return (
        f"{compiled_prompt}\n\n"
        "## Claude Code Execution\n"
        "You are running inside the target repository through the local Claude Code CLI. "
        "Execute the task using the available Claude Code tools, including reading files, "
        "editing files, and running verification commands when appropriate. Do not only "
        "describe the work unless the active permission mode prevents edits.\n\n"
        f"Operator objective: {objective}\n\n"
        "When finished, return a concise summary with files changed, commands run, tests "
        "or checks performed, and any remaining risks."
    )


def _claude_model_arg(model: str) -> str | None:
    lowered = model.lower()
    if "opus" in lowered:
        return "opus"
    if "sonnet" in lowered:
        return "sonnet"
    if "haiku" in lowered:
        return "haiku"
    return None


def _claude_code_env(env: dict[str, str] | None) -> dict[str, str]:
    values = dict(os.environ)
    if env is not None:
        values.update(env)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_TOKEN",
        "CRAIK_ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        values.pop(name, None)
    _emit_claude_code_progress("Using Claude CLI auth; bearer token env vars removed.")
    return values


def _safe_cli_detail(output: str) -> str:
    return " ".join(output.split())[:300]


def _clip_block(output: str, *, limit: int = 2000) -> str:
    if len(output) <= limit:
        return output
    return output[: limit - 1].rstrip() + "\n..."


def _project_for_cwd(store: LocalStore) -> ProjectProfile:
    registry = ProjectRegistry(store)
    return registry.add_project(Path.cwd())


def _title_from_prompt(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt).strip()
    if not normalized:
        return "TUI run"
    return normalized[:60].rstrip(" .,;:") or "TUI run"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _active_model(env: dict[str, str] | None) -> str:
    active_model = ModelSettingsStore.from_env(env).load().active_model
    return active_model or "anthropic/claude-sonnet-4-20250514"


def anthropic_uses_claude_cli_marker(env: dict[str, str] | None) -> bool:
    provider_id, _model = _active_provider_and_model(env)
    if provider_id != "provider_anthropic":
        return False
    try:
        profile = AuthProfileStore.from_env(env).get("anthropic:default")
    except AuthProfileStoreError:
        return False
    return (
        profile.kind is CredentialKind.MARKER
        and profile.metadata.get("external_runtime") == "claude-cli"
    )


def _active_provider_and_model(env: dict[str, str] | None) -> tuple[str, str | None]:
    settings = ModelSettingsStore.from_env(env).load()
    active_profile = settings.active_profile
    if active_profile is not None:
        return active_profile.provider_id, active_profile.model
    active_model = settings.active_model
    if not active_model:
        return "provider_openai", None
    provider_name = active_model.split("/", 1)[0]
    model = active_model.split("/", 1)[1] if "/" in active_model else None
    provider_id = {
        "anthropic": "provider_anthropic",
        "claude": "provider_anthropic",
        "openai": "provider_openai",
        "gemini": "provider_gemini",
        "google": "provider_gemini",
        "openai-compatible": "provider_local_openai_compatible",
        "local": "provider_local_openai_compatible",
        "ollama": "provider_local_ollama",
        "lm-studio": "provider_local_lm_studio",
        "vllm": "provider_local_vllm",
    }.get(provider_name, provider_name)
    return provider_id, model


def _claude_permission_mode(env: dict[str, str] | None) -> str | None:
    values = env or {}
    mode = values.get("CRAIK_CLAUDE_PERMISSION_MODE")
    return mode if mode in {"default", "acceptEdits", "plan", "auto"} else None


def _claude_code_command_summary(env: dict[str, str] | None) -> str:
    model = _active_model(env)
    parts = ["claude", "--tools", "default", "--output-format", "stream-json", "--verbose"]
    model_arg = _claude_model_arg(model)
    if model_arg:
        parts.extend(["--model", model_arg])
    permission_mode = _claude_permission_mode(env)
    if permission_mode:
        parts.extend(["--permission-mode", permission_mode])
    parts.extend(["-p", "<compiled Craik prompt>"])
    return " ".join(parts)


def _clip_summary(text: str, *, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized or "Claude Code completed without output."
    return normalized[: limit - 1].rstrip() + "..."


# Backward-compatible private alias for older imports and tests.
_create_and_execute_claude_code_run = execute_claude_code_run
