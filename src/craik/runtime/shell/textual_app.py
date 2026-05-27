"""Textual application for Craik's canonical interactive terminal runtime."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import OptionList, RichLog

from craik import __version__
from craik.runtime.backend.claude_code import (
    CLAUDE_CODE_RUN_APPROVED_ENV,
    CLAUDE_PERMISSION_MODE_ENV,
    claude_code_progress,
)
from craik.runtime.backend.client import GatewaySessionClient
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.session import claude_structured_event_to_backend_event
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.contract.dispatch import (
    InteractivePromptRequest,
)
from craik.runtime.contract.dispatch import (
    invoke_slash_command as _contract_invoke,
)
from craik.runtime.contract.format import format_command_result
from craik.runtime.shell.confirmations import (
    confirmation_request_for_text,
    record_confirmation_decision,
)
from craik.runtime.shell.contract_runtime.builtin_slash_commands import (
    run_command,
)
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry
from craik.runtime.shell.contract_runtime.result_adapter import to_slash_command_result
from craik.runtime.shell.external_editor import edit_text_externally
from craik.runtime.shell.inline_actions import handle_inline_action
from craik.runtime.shell.modals.textual_flow import open_textual_modal_flow
from craik.runtime.shell.readiness import ReadinessReport
from craik.runtime.shell.shell_history import append_history
from craik.runtime.shell.shell_invocation import (
    is_shell_invocation_text,
    run_shell_invocation,
)
from craik.runtime.shell.slash_command_schema.results import SlashCommandResult
from craik.runtime.shell.slash_completer import complete_slash_input
from craik.runtime.shell.textual_widgets.accent_emission import AccentEmission
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmationRequest, ConfirmModal
from craik.runtime.shell.textual_widgets.craik_input import (
    CraikInput,
    cli_prefix_warning,
    continue_multiline_value,
    should_continue_on_submit,
    slash_command_conversion,
)
from craik.runtime.shell.textual_widgets.footer_safe_area import FooterSafeArea
from craik.runtime.shell.textual_widgets.history_search import HistorySearchOverlay
from craik.runtime.shell.textual_widgets.inline_action_table import InlineActionTable
from craik.runtime.shell.textual_widgets.run_activity_panel import (
    RunActivityPanel,
    RunActivityState,
)
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.shell.textual_widgets.text_selection_hint import first_launch_selection_hint
from craik.runtime.shell.textual_widgets.theme_settings import (
    resolve_textual_theme as resolve_textual_theme,
)
from craik.runtime.shell.textual_widgets.theme_settings import (
    terminal_supports_textual as terminal_supports_textual,
)
from craik.runtime.shell.textual_widgets.toast_queue import ToastQueue, ToastSeverity
from craik.runtime.shell.textual_widgets.transcript_row_hint import TranscriptRowHint
from craik.runtime.shell.textual_widgets.transcript_search import TranscriptSearchOverlay
from craik.runtime.shell.textual_widgets.working_indicator import WorkingIndicator
from craik.runtime.shell.transcript_renderers import (
    render_claude_event,
    render_claude_run_summary,
    render_model_message,
    render_run_summary,
    render_user_message,
)
from craik.runtime.shell.tui_interactive_prompts import open_interactive_prompt_modal
from craik.runtime.status import auto_approve_status_payload

__all__ = ["CraikApp", "resolve_textual_theme", "run_textual_tui", "terminal_supports_textual"]

CLAUDE_PERMISSION_MODE_CYCLE = ("default", "acceptEdits", "plan", "auto")
CLAUDE_PERMISSION_MODE_LABELS = {
    "default": "Default",
    "acceptEdits": "Accept edits",
    "plan": "Plan",
    "auto": "Auto",
}


@dataclass(frozen=True, slots=True)
class _ActivityDetails:
    tool: str | None = None
    target: str | None = None
    phase: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    files: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()


class CraikApp(App[None]):
    """Chat-first terminal UI with transcript, input, and bottom status bar."""

    CSS_PATH = "textual_app_dark.tcss"
    ALLOW_SELECT = True
    BINDINGS = [
        ("ctrl+d", "quit", "Exit"),
        ("ctrl+f", "transcript_search", "Find"),
        ("ctrl+r", "history_search", "History"),
        ("ctrl+g", "external_editor", "Editor"),
        ("ctrl+x", "external_editor_prefix", "Editor Prefix"),
        ("ctrl+c", "interrupt_run", "Stop"),
        ("ctrl+y", "copy_transcript", "Copy"),
        Binding(
            "backtab,shift+tab",
            "cycle_claude_permission_mode",
            "Mode",
            priority=True,
        ),
        ("shift+enter", "insert_newline", "Newline"),
        ("ctrl+j", "insert_newline", "Newline"),
        ("alt+enter", "insert_newline", "Newline"),
        ("escape", "hide_popup", "Dismiss"),
    ]

    readiness: reactive[ReadinessReport | None] = reactive(None)

    def __init__(
        self,
        *,
        env: dict[str, str] | None = None,
        registry: AutoSlashRegistry | None = None,
    ) -> None:
        super().__init__()
        self.env = dict(os.environ) if env is None else dict(env)
        self.env["CRAIK_TUI"] = "1"
        self.registry = registry or get_tui_registry()
        self._editor_prefix_pending = False
        self._forgot_slash_pending: tuple[str, str] | None = None
        self._transcript_lines: list[str] = []
        self._last_copyable_output: str | None = None
        self._model_prompt_active = False
        self._working_started_at: float | None = None
        self._working_timer: Any | None = None
        self._active_claude_process: subprocess.Popen[str] | None = None
        self._active_claude_cancel: threading.Event | None = None
        self._active_claude_lock = threading.Lock()
        self._claude_code_approval_inflight = False
        self._queued_inputs: list[str] = []
        self._selected_transcript_rows: set[int] = set()
        self._selection_anchor: int | None = None
        self._run_backend_label: str | None = None
        self._last_run_event: str | None = None
        self._current_run_tool: str | None = None
        self._current_run_target: str | None = None
        self._current_run_phase: str | None = None
        self._current_run_id: str | None = None
        self._current_task_id: str | None = None
        self._run_files: list[str] = []
        self._run_commands: list[str] = []
        self._run_recent_events: list[str] = []
        self._run_approvals = 0
        self._run_denials = 0

    def compose(self) -> ComposeResult:
        yield RichLog(id="transcript", markup=True, wrap=True)
        with Container(id="slash-popup"):
            yield OptionList(id="slash-options")
        yield HistorySearchOverlay(env=self.env, id="history-search")
        yield TranscriptSearchOverlay(id="transcript-search")
        yield FooterSafeArea("", id="footer-safe-area")
        yield StatusBar(id="status", classes="status-bar")
        yield AccentEmission("", id="accent-emission")
        yield CraikInput(placeholder="Type a prompt or /help", id="input")
        yield ToastQueue(id="toast-queue")
        yield RunActivityPanel("", id="run-activity")
        yield TranscriptRowHint("", id="transcript-row-hint")
        yield WorkingIndicator("", id="working")

    def on_mount(self) -> None:
        from craik.runtime.shell.readiness import resolve_readiness

        report = resolve_readiness(self.env, in_tui=True)
        self.readiness = report
        mode = "audited" if report.operator_required else "single-operator"
        self._write_transcript(
            f"Welcome to Craik {__version__}. Mode: {mode}. Type a prompt or /help."
        )
        self.query_one("#status", StatusBar).update_status(
            report,
            cwd=Path.cwd(),
            auto_approve=auto_approve_status_payload(self.env) is not None,
            session_name=self.env.get("CRAIK_SESSION_NAME"),
            claude_mode=_claude_permission_mode_label(self.env),
            backend=self._run_backend_label,
            run_state="running" if self._model_prompt_active else None,
        )
        self.query_one("#slash-popup", Container).display = False
        self.query_one("#history-search", HistorySearchOverlay).display = False
        self.query_one("#transcript-search", TranscriptSearchOverlay).display = False
        self.query_one("#working", WorkingIndicator).display = False
        self.query_one("#run-activity", RunActivityPanel).display = False
        self.query_one("#transcript-row-hint", TranscriptRowHint).display = False
        self.query_one("#toast-queue", ToastQueue).display = False
        if auto_approve_status_payload(self.env) is not None:
            self._flash_accent("state")
        if selection_hint := first_launch_selection_hint(self.env):
            self._toast(selection_hint)
        self.query_one("#input", CraikInput).focus()

    def on_input_changed(self, event: CraikInput.Changed) -> None:
        value = event.value
        if value.startswith("/"):
            self._show_slash_popup(value)
        else:
            self.query_one("#slash-popup", Container).display = False

    def on_input_submitted(self, event: CraikInput.Submitted) -> None:
        input_widget = self.query_one("#input", CraikInput)
        if should_continue_on_submit(event.value):
            input_widget.value = continue_multiline_value(event.value)
            input_widget.cursor_position = len(input_widget.value)
            event.stop()
            return
        conversion = slash_command_conversion(event.value)
        if conversion is not None:
            pending = self._forgot_slash_pending
            if pending != (event.value, conversion):
                self._forgot_slash_pending = (event.value, conversion)
                self._toast(
                    (
                        f"Did you mean `{conversion.split()[0]}`? "
                        "Press Tab to convert, Enter to send to the model."
                    ),
                    severity="warning",
                )
                event.stop()
                return
            self._forgot_slash_pending = None
        self._submit_text(event.value)

    def _submit_text(self, value: str, *, skip_confirmation: bool = False) -> None:
        text = value.strip()
        input_widget = self.query_one("#input", CraikInput)
        if not text:
            return
        warning = cli_prefix_warning(text)
        if warning is not None:
            self.notify(warning, severity="warning", timeout=8)
            return
        if text in {"/copy", "/copy last", "/copy latest", "/copy response", "/copy output"}:
            self._copy_latest_output()
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if text in {"/copy selection", "/copy selected"}:
            self._copy_selected_transcript_rows()
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if text in {"/copy transcript", "/copy all"}:
            self.action_copy_transcript()
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if text.startswith("/export transcript"):
            self._export_transcript()
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if text in {"/interrupt", "/stop"}:
            self.action_interrupt_run()
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if self._model_prompt_active and not skip_confirmation:
            self._queue_input(text)
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        confirmation = (
            None
            if skip_confirmation
            else confirmation_request_for_text(
                text,
                transcript_line_count=len(self._transcript_lines),
                active_profile=self._active_profile(),
            )
        )
        if (
            confirmation is None
            and not skip_confirmation
            and _requires_claude_code_run_approval(text, env=self.env)
            and self.env.get(CLAUDE_CODE_RUN_APPROVED_ENV) != "1"
        ):
            confirmation = _claude_code_run_approval_request(
                text,
                mode=_claude_permission_mode_label(self.env) or "Default",
            )
        if confirmation is not None:
            self.push_screen(
                ConfirmModal(confirmation),
                lambda confirmed: self._complete_confirmation(confirmation, confirmed),
            )
            return
        self._write_transcript(_user_transcript_markup(text), plain_text=f"> {text}")
        append_history(text, env=self.env)
        if is_shell_invocation_text(text):
            try:
                shell_result = run_shell_invocation(text, env=self.env, cwd=Path.cwd())
            except ValueError as error:
                self._write_transcript(str(error))
            else:
                self._write_transcript(shell_result.transcript_text)
                self._flash_accent("receipt")
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if self._open_modal_flow(text):
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if text.startswith("/"):
            self._dispatch_slash_async(text)
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        self._dispatch_prompt_async(text)
        input_widget.value = ""
        self.query_one("#slash-popup", Container).display = False

    def on_key(self, event: events.Key) -> None:
        if self._editor_prefix_pending:
            self._editor_prefix_pending = False
            if event.key == "ctrl+e":
                self.action_external_editor()
                event.stop()
                return
        if self._forgot_slash_pending is not None:
            original, conversion = self._forgot_slash_pending
            if event.key == "escape":
                self._forgot_slash_pending = None
                event.stop()
                return
            if event.key == "tab":
                self._forgot_slash_pending = None
                input_widget = self.query_one("#input", CraikInput)
                input_widget.value = conversion
                self._submit_text(conversion)
                event.stop()
                return
            if event.key != "enter":
                input_widget = self.query_one("#input", CraikInput)
                if input_widget.value != original:
                    self._forgot_slash_pending = None
        overlay = self.query_one("#history-search", HistorySearchOverlay)
        transcript_search = self.query_one("#transcript-search", TranscriptSearchOverlay)
        if transcript_search.display:
            if event.key == "escape":
                transcript_search.dismiss()
                self.query_one("#input", CraikInput).focus()
                event.stop()
                return
            if event.key == "backspace":
                transcript_search.backspace()
                event.stop()
                return
            if event.key == "enter":
                transcript_search.move(1)
                event.stop()
                return
            if event.character and event.character.isprintable():
                transcript_search.append_query(event.character)
                event.stop()
                return
        if not overlay.display:
            return
        if event.key == "escape":
            overlay.dismiss()
            event.stop()
            return
        if event.key == "ctrl+s":
            overlay.cycle_scope()
            event.stop()
            return
        if event.key == "up":
            overlay.move(-1)
            event.stop()
            return
        if event.key == "down":
            overlay.move(1)
            event.stop()
            return
        if event.key == "backspace":
            overlay.backspace()
            event.stop()
            return
        if event.key == "tab":
            self._apply_history_selection(submit=False)
            event.stop()
            return
        if event.key == "enter":
            self._apply_history_selection(submit=True)
            event.stop()
            return
        if event.character and event.character.isprintable():
            overlay.append_query(event.character)
            event.stop()

    def action_hide_popup(self) -> None:
        self.query_one("#slash-popup", Container).display = False
        self.query_one("#history-search", HistorySearchOverlay).dismiss()
        self.query_one("#transcript-search", TranscriptSearchOverlay).dismiss()
        self.query_one("#toast-queue", ToastQueue).dismiss()

    def action_history_search(self) -> None:
        overlay = self.query_one("#history-search", HistorySearchOverlay)
        if overlay.display:
            overlay.move(1)
            return
        overlay.open()

    def action_transcript_search(self) -> None:
        overlay = self.query_one("#transcript-search", TranscriptSearchOverlay)
        if overlay.display:
            overlay.move(1)
            return
        overlay.open(self._transcript_lines)
        overlay.focus()

    def action_external_editor(self) -> None:
        input_widget = self.query_one("#input", CraikInput)
        result = edit_text_externally(input_widget.value, env=self.env)
        if result.warning:
            self.notify(result.warning, severity="warning", timeout=8)
            return
        input_widget.value = result.text

    def action_external_editor_prefix(self) -> None:
        self._editor_prefix_pending = True
        self.notify("Press Ctrl+E to open the external editor.", timeout=3)

    def action_copy_transcript(self) -> None:
        if self._selected_transcript_rows:
            self._copy_selected_transcript_rows()
            return
        text = "\n".join(self._transcript_lines).strip()
        if not text:
            self._toast("Transcript is empty.", severity="information")
            return
        self.copy_to_clipboard(text)
        self._toast("Transcript copied.", severity="information")

    def action_interrupt_run(self) -> None:
        if not self._interrupt_active_claude_code_run():
            self._toast("No interruptible Claude Code run is active.", severity="information")

    def action_insert_newline(self) -> None:
        input_widget = self.query_one("#input", CraikInput)
        input_widget.value = continue_multiline_value(input_widget.value)
        input_widget.cursor_position = len(input_widget.value)

    def action_cycle_claude_permission_mode(self) -> None:
        current = self.env.get(CLAUDE_PERMISSION_MODE_ENV, "default")
        try:
            index = CLAUDE_PERMISSION_MODE_CYCLE.index(current)
        except ValueError:
            index = 0
        next_mode = CLAUDE_PERMISSION_MODE_CYCLE[(index + 1) % len(CLAUDE_PERMISSION_MODE_CYCLE)]
        self.env[CLAUDE_PERMISSION_MODE_ENV] = next_mode
        label = CLAUDE_PERMISSION_MODE_LABELS[next_mode]
        self._toast(f"Claude mode: {label}", severity="information")
        self._refresh_status_bar()
        self._flash_accent("state")

    def _apply_history_selection(self, *, submit: bool) -> None:
        overlay = self.query_one("#history-search", HistorySearchOverlay)
        selection = overlay.selected(submit=submit)
        if selection is None:
            return
        input_widget = self.query_one("#input", CraikInput)
        input_widget.value = selection.text
        overlay.dismiss()
        if selection.submit:
            self._submit_text(selection.text)

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

    def _dispatch_contract(self, text: str) -> CommandResult:
        """Dispatch slash text through the CLI/TUI contract layer."""
        return _contract_invoke(
            text,
            registry=self.registry,
            env=self.env,
            interactive_prompt_handler=self._open_modal_for_request,
        )

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
            gateway_result = GatewaySessionClient(
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

    def _set_active_claude_process(self, process: subprocess.Popen[str] | None) -> None:
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

    def _open_modal_flow(self, text: str) -> bool:
        return open_textual_modal_flow(self, text)

    def _complete_confirmation(
        self,
        request: ConfirmationRequest,
        confirmed: bool | None,
    ) -> None:
        self.query_one("#input", CraikInput).value = ""
        self.query_one("#slash-popup", Container).display = False
        decision = "confirmed" if confirmed else "declined"
        self._record_confirmation_decision(request.command_text, decision)
        if not confirmed:
            self._toast(f"Canceled `{request.command_text}`.", severity="information")
            return
        if request.command_text == "/clear":
            self.query_one("#transcript", RichLog).clear()
            self._transcript_lines.clear()
            self._write_transcript("Transcript cleared. Receipts remain audited.")
            self._toast("Transcript cleared.", severity="information")
            return
        if _requires_claude_code_run_approval(request.command_text, env=self.env):
            self.env[CLAUDE_CODE_RUN_APPROVED_ENV] = "1"
            self._claude_code_approval_inflight = True
            self._write_transcript(
                "Claude Code run authority approved for this TUI dispatch.",
                plain_text="Claude Code run authority approved for this TUI dispatch.",
            )
        self._submit_text(request.command_text, skip_confirmation=True)

    def on_inline_action_table_inline_action_requested(
        self,
        message: InlineActionTable.InlineActionRequested,
    ) -> None:
        handle_inline_action(self, message)

    def _record_confirmation_decision(self, command_text: str, decision: str) -> None:
        error = record_confirmation_decision(command_text, decision, env=self.env)
        if error is not None:
            self._toast(
                error,
                severity="error",
            )

    def _write_transcript(self, value: object, *, plain_text: str | None = None) -> None:
        self.query_one("#transcript", RichLog).write(value)
        line = str(value if plain_text is None else plain_text)
        self._transcript_lines.append(line)
        if line.strip() and not _non_response_transcript_line(line):
            self._last_copyable_output = line

    def _active_profile(self) -> str:
        report = self.readiness
        if report is not None:
            return report.active_profile
        return "openai:default"

    def _active_model_label(self) -> str:
        report = self.readiness
        active_model = report.active_model if report is not None else None
        return _display_model_label(active_model)

    def _show_slash_popup(self, prefix: str) -> None:
        popup = self.query_one("#slash-popup", Container)
        options = self.query_one("#slash-options", OptionList)
        options.clear_options()
        for candidate in complete_slash_input(prefix, env=self.env, registry=self.registry)[:12]:
            label = candidate.value
            if candidate.description:
                label = f"{candidate.value}  {candidate.description}"
            options.add_option(label)
        popup.display = True

    def _select_transcript_row(self, row: int, *, extend: bool) -> None:
        if extend and self._selection_anchor is not None:
            start, end = sorted((self._selection_anchor, row))
            self._selected_transcript_rows = set(range(start, end + 1))
        else:
            self._selection_anchor = row
            self._selected_transcript_rows = {row}
        self._update_transcript_selection_hint()

    def _update_transcript_selection_hint(self) -> None:
        hint = self.query_one("#transcript-row-hint", TranscriptRowHint)
        count = len(self._selected_transcript_rows)
        if count == 0:
            hint.display = False
            return
        hint.display = True
        plural = "s" if count != 1 else ""
        hint.update(f"{count} transcript row{plural} selected · /copy selection")

    def _copy_selected_transcript_rows(self) -> None:
        rows = [
            self._transcript_lines[index]
            for index in sorted(self._selected_transcript_rows)
            if 0 <= index < len(self._transcript_lines)
        ]
        if not rows:
            self._toast("No transcript rows selected.", severity="information")
            return
        self.copy_to_clipboard("\n".join(rows))
        self._toast(f"Copied {len(rows)} selected row(s).", severity="information")

    def _copy_latest_output(self) -> None:
        text = (self._last_copyable_output or "").strip()
        if not text:
            text = _latest_copyable_transcript_line(self._transcript_lines)
        if not text:
            self._toast("No response output is available to copy.", severity="information")
            return
        self.copy_to_clipboard(text)
        self._toast("Latest response copied.", severity="information")

    def _export_transcript(self) -> None:
        from craik.runtime.paths import ensure_craik_home

        target_dir = ensure_craik_home(self.env).state / "exports"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"transcript-{int(time.time())}.txt"
        target.write_text("\n".join(self._transcript_lines).strip() + "\n", encoding="utf-8")
        self._write_transcript(f"Transcript exported to `{target}`.", plain_text=str(target))

    def _queue_input(self, text: str) -> None:
        self._queued_inputs.append(text)
        self._write_transcript(
            f"[dim]Queued input #{len(self._queued_inputs)}:[/dim] {escape(text)}",
            plain_text=f"Queued input #{len(self._queued_inputs)}: {text}",
        )
        self.query_one("#input", CraikInput).placeholder = self._active_input_placeholder()
        self._toast("Input queued until the active run finishes.", severity="information")
        self._refresh_run_activity()

    def _drain_input_queue(self) -> None:
        if self._model_prompt_active or not self._queued_inputs:
            return
        next_text = self._queued_inputs.pop(0)
        if self._model_prompt_active:
            self.query_one("#input", CraikInput).placeholder = self._active_input_placeholder()
        self._refresh_run_activity()
        self._submit_text(next_text)

    def _active_input_placeholder(self) -> str:
        backend = self._run_backend_label or "model"
        queued = len(self._queued_inputs)
        if queued:
            return f"{backend} is running · {queued} queued · type another prompt or /stop"
        return f"{backend} is running · type next prompt to queue, or /stop"

    def _append_recent_run_event(self, message: str) -> None:
        event = " ".join(message.split())
        if len(event) > 72:
            event = event[:71].rstrip() + "..."
        if self._run_recent_events and self._run_recent_events[-1] == event:
            return
        self._run_recent_events.append(event)
        del self._run_recent_events[:-3]

    def _reset_run_activity(self) -> None:
        self._last_run_event = None
        self._current_run_tool = None
        self._current_run_target = None
        self._current_run_phase = "starting"
        self._current_run_id = None
        self._current_task_id = None
        self._run_files.clear()
        self._run_commands.clear()
        self._run_recent_events.clear()
        self._run_approvals = 0
        self._run_denials = 0
        self._refresh_run_activity()

    def _update_run_activity_from_message(self, message: str) -> None:
        self._last_run_event = message
        self._append_recent_run_event(message)
        details = _activity_details(message)
        if details.tool:
            self._current_run_tool = details.tool
        if details.target:
            self._current_run_target = details.target
        if details.phase:
            self._current_run_phase = details.phase
        if details.run_id:
            self._current_run_id = details.run_id
        if details.task_id:
            self._current_task_id = details.task_id
        for path in details.files:
            if path not in self._run_files:
                self._run_files.append(path)
        for command in details.commands:
            if command not in self._run_commands:
                self._run_commands.append(command)
        lowered = message.lower()
        if "approval approved" in lowered or "approved claude code" in lowered:
            self._run_approvals += 1
        if "permission denied" in lowered or "approval denied" in lowered:
            self._run_denials += 1
        self._refresh_run_activity()

    def _update_run_activity_from_gateway_event(self, event: dict[str, object]) -> None:
        message = _gateway_event_message(event)
        if message is None:
            return
        data = event.get("data")
        event_type = str(event.get("type") or "gateway.event")
        self._last_run_event = message
        self._append_recent_run_event(message)
        run_id = event.get("run_id")
        task_id = event.get("task_id")
        if isinstance(run_id, str) and run_id:
            self._current_run_id = run_id
        if isinstance(task_id, str) and task_id:
            self._current_task_id = task_id
        if event_type == "prompt.submitted":
            self._current_run_phase = "submitted"
        elif event_type == "model.selected":
            self._current_run_phase = "thinking"
            model_label = _gateway_model_label(data)
            if model_label:
                self._run_backend_label = model_label
                self._refresh_status_bar()
        elif event_type == "run.working":
            self._current_run_phase = _data_string(data, "phase") or "thinking"
        elif event_type == "run.started":
            self._current_run_phase = "running"
        elif event_type == "tool.used":
            self._current_run_phase = "using tool"
            tool = _data_string(data, "tool")
            target = _data_string(data, "target")
            command = _data_string(data, "command")
            if tool:
                self._current_run_tool = tool
            if target:
                self._current_run_target = target
            if command and command not in self._run_commands:
                self._run_commands.append(command)
            for path in _data_string_list(data, "files"):
                if path not in self._run_files:
                    self._run_files.append(path)
        elif event_type == "file.changed":
            self._current_run_phase = "changing files"
            tool = _data_string(data, "tool")
            target = _data_string(data, "target")
            if tool:
                self._current_run_tool = tool
            if target:
                self._current_run_target = target
            for path in _data_string_list(data, "files"):
                if path not in self._run_files:
                    self._run_files.append(path)
        elif event_type == "approval.requested":
            self._current_run_phase = "approval requested"
            self._run_approvals += 1
            tool = _data_string(data, "tool")
            target = _data_string(data, "target")
            if tool:
                self._current_run_tool = tool
            if target:
                self._current_run_target = target
                if target not in self._run_files:
                    self._run_files.append(target)
        elif event_type == "approval.denied":
            self._current_run_phase = "approval denied"
            self._run_denials += 1
        elif event_type == "receipt.created":
            self._current_run_phase = "recording receipt"
        elif event_type == "run.output":
            self._current_run_phase = "writing output"
        elif event_type == "run.completed":
            self._current_run_phase = "completed"
        elif event_type == "approval.resolved":
            decision = _data_string(data, "decision")
            if decision == "approved":
                self._run_approvals += 1
            elif decision == "denied":
                self._run_denials += 1
        elif event_type == "error":
            self._current_run_phase = "error"
        self._refresh_run_activity()

    def _refresh_run_activity(self) -> None:
        if not self._model_prompt_active:
            return
        elapsed = 0
        if self._working_started_at is not None:
            elapsed = int(time.monotonic() - self._working_started_at)
        self.query_one("#run-activity", RunActivityPanel).update_activity(
            RunActivityState(
                backend=self._run_backend_label or "model",
                elapsed_seconds=elapsed,
                mode=_claude_permission_mode_label(self.env),
                phase=self._current_run_phase,
                run_id=self._current_run_id,
                task_id=self._current_task_id,
                current_tool=self._current_run_tool,
                current_target=self._current_run_target,
                files=tuple(self._run_files),
                commands=tuple(self._run_commands),
                last_event=self._last_run_event,
                recent_events=tuple(self._run_recent_events),
                approvals=self._run_approvals,
                denials=self._run_denials,
                queued=len(self._queued_inputs),
            )
        )


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
        "gemini": "Google",
        "google": "Google",
        "fixture": "Fixture",
    }.get(provider, _title_model_id(provider))
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
        or stripped.startswith("Claude Code:")
        or stripped.startswith("Transcript exported to ")
        or stripped in {"Audited run summary", "Transcript cleared. Receipts remain audited."}
    )


def _uses_model_backed_slash_execution(text: str) -> bool:
    try:
        tokens = shlex.split(text.strip())
    except ValueError:
        tokens = text.strip().split()
    if not tokens or tokens[0] != "/run":
        return False
    for index, token in enumerate(tokens[1:], start=1):
        if token == "--backend":
            return index + 1 < len(tokens) and tokens[index + 1] == "claude-code"
        if token == "--backend=claude-code":
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
    return (
        isinstance(payload, dict)
        and payload.get("schema")
        in {
            "craik.provider_backed_run_execution",
            "craik.claude_code_run_execution",
        }
    )


def _claude_code_run_approval_request(text: str, *, mode: str = "Default") -> ConfirmationRequest:
    posture = _claude_permission_mode_posture(mode)
    message = (
        "Approve this Claude Code run once?\n\n"
        f"Current mode: {mode} — {posture}\n\n"
        "- Read repository: .\n"
        "- Write documentation: docs/, README.md, CHANGELOG.md\n"
        "- Write Craik receipts and handoffs\n"
        "- Run verification commands\n\n"
        "Use Ctrl+C or /stop to interrupt the run after it starts."
    )
    return ConfirmationRequest(
        text,
        "Approve Claude Code run authority?",
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


def _claude_permission_mode_label(env: dict[str, str]) -> str | None:
    mode = env.get(CLAUDE_PERMISSION_MODE_ENV)
    if mode is None or mode == "default":
        return None
    return CLAUDE_PERMISSION_MODE_LABELS.get(mode, mode)


def _claude_permission_mode_posture(mode: str) -> str:
    normalized = mode.lower()
    if normalized == "plan":
        return "Claude Code should preview intent without editing."
    if normalized == "accept edits":
        return "file edits can proceed with fewer prompts."
    if normalized == "auto":
        return "Claude Code tools can proceed with minimal interruption."
    return "Claude Code follows its normal tool permission gates."


def run_textual_tui(*, env: dict[str, str] | None = None) -> int:
    """Run the Textual app and return a process-style exit code."""
    app = CraikApp(env=env)
    result = app.run()
    return int(result or 0)
