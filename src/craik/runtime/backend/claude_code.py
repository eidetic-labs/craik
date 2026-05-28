"""Claude Code Gateway backend execution and provenance capture."""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from craik.contracts.models import (
    CapabilityReceipt,
    ReceiptResult,
    RunOutput,
)
from craik.runtime.backend.claude_code_attestations import (
    _claude_code_execution_prompt,
    _claude_model_arg,
    _put_claude_code_tool_attestations,
)
from craik.runtime.backend.claude_code_grants import (
    _put_claude_code_approval_receipt,
    _put_claude_code_grants,
    _require_claude_code_run_approval,
)
from craik.runtime.backend.claude_code_hooks import (
    chain_event_callbacks,
    chain_process_callbacks,
    chain_progress_callbacks,
)
from craik.runtime.backend.claude_code_process import (
    ClaudeProcessProtocol,
    _read_claude_code_stdout,
    _terminate_claude_code_process,
)
from craik.runtime.backend.claude_code_settings import (
    _active_model,
    _claude_code_command_summary,
    _claude_permission_mode,
    _project_for_cwd,
    _title_from_prompt,
    anthropic_uses_claude_cli_marker,
)
from craik.runtime.backend.claude_code_support import (
    _claude_activity_summary,
    _claude_completion_fallback,
    _claude_stream_line_events,
    _clip_summary,
    _safe_cli_detail,
)
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

_CLAUDE_CODE_PROCESS: ContextVar[Callable[[ClaudeProcessProtocol | None], None] | None] = (
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
    """Raised when the operator interrupts a local Claude run."""


@contextmanager
def claude_code_progress(
    callback: Callable[[str], None] | None,
    *,
    event_callback: Callable[[dict[str, object]], None] | None = None,
    process_callback: Callable[[ClaudeProcessProtocol | None], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Iterator[None]:
    """Install per-dispatch Claude Code progress and cancellation hooks."""
    progress_token = _CLAUDE_CODE_PROGRESS.set(
        chain_progress_callbacks(_CLAUDE_CODE_PROGRESS.get(), callback)
    )
    event_token = _CLAUDE_CODE_EVENT.set(
        chain_event_callbacks(_CLAUDE_CODE_EVENT.get(), event_callback)
    )
    process_token = _CLAUDE_CODE_PROCESS.set(
        chain_process_callbacks(_CLAUDE_CODE_PROCESS.get(), process_callback)
    )
    cancel_token = _CLAUDE_CODE_CANCEL.set(cancel_event or _CLAUDE_CODE_CANCEL.get())
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
        _emit_claude_code_progress("Preparing audited model run.")
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
            tests_run=["Local Anthropic CLI run executed from the TUI"],
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
        raise ClaudeCodeInterrupted("Audited run interrupted by operator.")
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


def _set_claude_code_process(process: ClaudeProcessProtocol | None) -> None:
    callback = _CLAUDE_CODE_PROCESS.get()
    if callback is not None:
        callback(process)

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
