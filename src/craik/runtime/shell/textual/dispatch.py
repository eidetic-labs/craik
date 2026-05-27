"""Dispatch and active-run methods for the Textual TUI app."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from textual.widgets import RichLog

from craik.runtime.backend.claude_code import CLAUDE_CODE_RUN_APPROVED_ENV, claude_code_progress
from craik.runtime.backend.client import GatewaySessionClient
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.session import claude_structured_event_to_backend_event
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.contract.dispatch import (
    InteractivePromptRequest,
)
from craik.runtime.contract.format import format_command_result
from craik.runtime.shell.contract_runtime.builtin_slash_commands import run_command
from craik.runtime.shell.contract_runtime.result_adapter import to_slash_command_result
from craik.runtime.shell.slash_command_schema.results import SlashCommandResult
from craik.runtime.shell.textual.support import (
    InterruptibleProcess,
    _audited_run_text,
    _claude_permission_mode_label,
    _claude_progress_markup,
    _is_audited_run_payload,
    _is_claude_code_run_result,
    _model_transcript_markup,
    _uses_model_backed_slash_execution,
)
from craik.runtime.shell.textual_widgets.accent_emission import AccentEmission
from craik.runtime.shell.textual_widgets.craik_input import CraikInput
from craik.runtime.shell.textual_widgets.run_activity_panel import RunActivityPanel
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.shell.textual_widgets.toast_queue import ToastQueue, ToastSeverity
from craik.runtime.shell.textual_widgets.working_indicator import WorkingIndicator
from craik.runtime.shell.transcript_renderers import (
    render_claude_run_summary,
    render_run_summary,
)
from craik.runtime.shell.tui_interactive_prompts import open_interactive_prompt_modal
from craik.runtime.status import auto_approve_status_payload


def _gateway_session_client_class() -> type[GatewaySessionClient]:
    from craik.runtime.shell import textual_app

    return getattr(textual_app, "GatewaySessionClient", GatewaySessionClient)


class CraikAppDispatchMixin:
    env: dict[str, str]
    registry: Any
    readiness: Any
    _transcript_lines: list[str]
    _last_copyable_output: str | None
    _model_prompt_active: bool
    _working_started_at: float | None
    _working_timer: Any | None
    _active_claude_process: InterruptibleProcess | None
    _active_claude_cancel: threading.Event | None
    _active_claude_lock: threading.Lock
    _claude_code_approval_inflight: bool
    _queued_inputs: list[str]
    _run_backend_label: str | None
    _last_run_event: str | None
    _current_run_phase: str | None

    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any:
            raise AttributeError(name)

    def _dispatch(self, text: str) -> SlashCommandResult:
        if text.startswith("/"):
            result = to_slash_command_result(self._dispatch_contract(text))
        else:
            result = to_slash_command_result(run_command(text, env=self.env))
        if (
            text.startswith("/model")
            or text.startswith("/mode")
            or text.startswith("/rename")
            or text.startswith("/theme")
        ):
            self._refresh_status_bar()
            self._flash_accent("state")
        return result

    def _dispatch_slash_async(self, text: str) -> None:
        """Dispatch slash commands off the UI thread so modal prompts can block safely."""
        # Interactive prompt interception is synchronous from Typer's point of view.
        # Keep the callback on a worker thread and marshal modal pushes/results
        # through call_from_thread so waiting for modal completion never freezes Textual.
        uses_model = _uses_model_backed_slash_execution(text)
        if uses_model:
            if self._model_prompt_active:
                self._queue_input(text)
                return
            self._run_backend_label = "Claude Code"
            self._prepare_active_claude_code_run()
            self._set_working(True)
            self._write_transcript(
                _claude_progress_markup("Dispatching Claude Code run."),
                plain_text="Claude Code: Dispatching Claude Code run.",
            )
        thread = threading.Thread(
            target=self._dispatch_slash_worker,
            args=(text,),
            name="craik-tui-slash-dispatch",
            daemon=True,
        )
        thread.start()

    def _dispatch_prompt_async(self, text: str) -> None:
        """Dispatch model prompts off the UI thread and show progress while waiting."""
        if self._model_prompt_active:
            self._queue_input(text)
            return
        self._run_backend_label = self._active_model_label()
        self._set_working(True)
        thread = threading.Thread(
            target=self._dispatch_prompt_worker,
            args=(text,),
            name="craik-tui-model-dispatch",
            daemon=True,
        )
        thread.start()

    def _dispatch_prompt_worker(self, text: str) -> None:
        try:
            gateway_client = _gateway_session_client_class()
            gateway_result = gateway_client(
                env=self.env,
                source="tui",
                event_handler=self._emit_gateway_event,
            ).submit_prompt(text)
            payload = gateway_result.payload_with_events()
            result = SlashCommandResult(
                _audited_run_text(payload) or "Audited run completed.",
                payload=payload,
                payload_shape="card",
            )
        except Exception as error:
            result = SlashCommandResult(
                f"Audited run failed: {error}",
                exit_code=2,
            )
        self.call_from_thread(self._complete_prompt_dispatch, result)

    def _complete_prompt_dispatch(self, result: SlashCommandResult) -> None:
        model_label = self._run_backend_label or self._active_model_label()
        self._set_working(False)
        if _is_audited_run_payload(result.payload):
            payload = cast(dict[str, object], result.payload)
            self.query_one("#transcript", RichLog).write(
                render_run_summary(payload, title="Audited run summary")
            )
            self._transcript_lines.append("Audited run summary")
            self._last_copyable_output = result.text
            self._transcript_lines.append(result.text)
        else:
            self._write_transcript(
                _model_transcript_markup(result.text, model_label=model_label),
                plain_text=result.text,
            )
        if result.exit_shell:
            self.exit()
            return
        self._drain_input_queue()

    def _dispatch_slash_worker(self, text: str) -> None:
        try:
            if _uses_model_backed_slash_execution(text):
                with claude_code_progress(
                    self._emit_claude_code_progress,
                    event_callback=self._emit_claude_code_event,
                    process_callback=self._set_active_claude_process,
                    cancel_event=self._active_claude_cancel,
                ):
                    contract_result = self._dispatch_contract(text)
            else:
                contract_result = self._dispatch_contract(text)
        except Exception as error:
            contract_result = CommandResult(
                payload=str(error),
                shape="markdown",
                text=str(error),
                exit_code=2,
            )
        self.call_from_thread(self._complete_slash_dispatch, contract_result)

    def _complete_slash_dispatch(self, contract_result: CommandResult) -> None:
        if self._claude_code_approval_inflight:
            self.env.pop(CLAUDE_CODE_RUN_APPROVED_ENV, None)
            self._claude_code_approval_inflight = False
        if self._model_prompt_active:
            self._set_working(False)
        self._clear_active_claude_code_run()
        transcript = self.query_one("#transcript", RichLog)
        result = to_slash_command_result(contract_result)
        if _is_claude_code_run_result(contract_result):
            transcript.write(render_claude_run_summary(contract_result.payload))
        else:
            transcript.write(format_command_result(contract_result, kind="tui"))
        if result.text.strip():
            self._last_copyable_output = result.text
        self._transcript_lines.append(result.text)
        if contract_result.command_name in {"model", "mode", "rename", "theme"}:
            self._refresh_status_bar()
            self._flash_accent("state")
        if result.exit_shell:
            self.exit()
            return
        self._drain_input_queue()

    def _emit_claude_code_progress(self, message: str) -> None:
        self.call_from_thread(self._update_run_activity_from_message, message)
        self.call_from_thread(
            self._write_transcript,
            _claude_progress_markup(message),
            plain_text=f"Claude Code: {message}",
        )

    def _emit_gateway_event(self, event: BackendEvent) -> None:
        self.call_from_thread(self._update_run_activity_from_gateway_event, event.as_dict())

    def _emit_claude_code_event(self, event: dict[str, object]) -> None:
        gateway_event = claude_structured_event_to_backend_event(event)
        self.call_from_thread(self._update_run_activity_from_gateway_event, gateway_event.as_dict())

    def _prepare_active_claude_code_run(self) -> None:
        with self._active_claude_lock:
            self._active_claude_cancel = threading.Event()
            self._active_claude_process = None

    def _set_active_claude_process(self, process: InterruptibleProcess | None) -> None:
        with self._active_claude_lock:
            self._active_claude_process = process

    def _clear_active_claude_code_run(self) -> None:
        with self._active_claude_lock:
            self._active_claude_process = None
            self._active_claude_cancel = None

    def _interrupt_active_claude_code_run(self) -> bool:
        with self._active_claude_lock:
            cancel_event = self._active_claude_cancel
            process = self._active_claude_process
            if cancel_event is None and process is None:
                return False
            if cancel_event is not None:
                cancel_event.set()
            if process is not None and process.poll() is None:
                process.terminate()
        self._write_transcript(
            _claude_progress_markup("Interrupt requested. Stopping Claude Code..."),
            plain_text="Claude Code: Interrupt requested. Stopping Claude Code...",
        )
        self._update_run_activity_from_message("Interrupt requested. Stopping Claude Code...")
        return True

    def _open_modal_for_request(self, request: InteractivePromptRequest) -> object:
        """Push a canonical modal for an intercepted prompt and wait for completion."""
        return open_interactive_prompt_modal(self, request)

    def _flash_accent(self, kind: str) -> None:
        self.query_one("#accent-emission", AccentEmission).flash(kind)

    def _refresh_status_bar(self) -> None:
        from craik.runtime.shell.readiness import resolve_readiness

        report = resolve_readiness(self.env, in_tui=True)
        self.readiness = report
        self.query_one("#status", StatusBar).update_status(
            report,
            cwd=Path.cwd(),
            auto_approve=auto_approve_status_payload(self.env) is not None,
            session_name=self.env.get("CRAIK_SESSION_NAME"),
            claude_mode=_claude_permission_mode_label(self.env),
            backend=self._run_backend_label,
            run_state="running" if self._model_prompt_active else None,
        )

    def _set_working(self, active: bool) -> None:
        indicator = self.query_one("#working", WorkingIndicator)
        input_widget = self.query_one("#input", CraikInput)
        activity = self.query_one("#run-activity", RunActivityPanel)
        self._model_prompt_active = active
        if active:
            self._working_started_at = time.monotonic()
            indicator.display = True
            activity.display = True
            self._reset_run_activity()
            if self._run_backend_label != "Claude Code":
                self._current_run_phase = "thinking"
                self._last_run_event = (
                    f"{self._run_backend_label} is thinking. You can keep typing to queue input."
                )
            indicator.set_elapsed(
                0,
                backend=self._run_backend_label,
                queued=len(self._queued_inputs),
            )
            self._refresh_run_activity()
            input_widget.disabled = False
            input_widget.placeholder = self._active_input_placeholder()
            if self._working_timer is None:
                self._working_timer = self.set_interval(1.0, self._tick_working)
            self._refresh_status_bar()
            return
        indicator.display = False
        activity.display = False
        input_widget.disabled = False
        input_widget.placeholder = "Type a prompt or /help"
        self._working_started_at = None
        self._run_backend_label = None
        if self._working_timer is not None:
            self._working_timer.stop()
            self._working_timer = None
        input_widget.focus()
        self._refresh_status_bar()

    def _tick_working(self) -> None:
        if self._working_started_at is None:
            return
        elapsed = int(time.monotonic() - self._working_started_at)
        self.query_one("#working", WorkingIndicator).set_elapsed(
            elapsed,
            backend=self._run_backend_label,
            queued=len(self._queued_inputs),
        )
        self._refresh_run_activity()

    def _toast(self, message: str, *, severity: ToastSeverity = "information") -> None:
        toast_queue = self.query_one("#toast-queue", ToastQueue)
        toast_queue.push(message, severity=severity)
        self.notify(message, severity=severity, timeout=8)
