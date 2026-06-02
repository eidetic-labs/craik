"""Textual application for Craik's canonical interactive terminal runtime."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import OptionList, RichLog

from craik import __version__
from craik.runtime.backend.claude_code import (
    CLAUDE_CODE_RUN_APPROVED_ENV,
)
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.contract.dispatch import (
    invoke_slash_command as _contract_invoke,
)
from craik.runtime.shell.confirmations import (
    confirmation_request_for_text,
)
from craik.runtime.shell.contract_runtime.mode_args import active_vendor_mode_spec
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry
from craik.runtime.shell.external_editor import edit_text_externally
from craik.runtime.shell.readiness import ReadinessReport
from craik.runtime.shell.shell_history import append_history
from craik.runtime.shell.shell_invocation import (
    is_shell_invocation_text,
    run_shell_invocation,
)
from craik.runtime.shell.textual.activity import CraikAppActivityMixin
from craik.runtime.shell.textual.dispatch import CraikAppDispatchMixin
from craik.runtime.shell.textual.support import (
    InterruptibleProcess,
    _active_permission_mode_display,
    _claude_permission_mode_label,
    _requires_claude_code_run_approval,
    _vendor_mode_display,
)
from craik.runtime.shell.textual.support import (
    _claude_code_run_approval_request as _claude_code_run_approval_request,
)
from craik.runtime.shell.textual.support import (
    _user_transcript_markup as _user_transcript_markup,
)
from craik.runtime.shell.textual_widgets.accent_emission import AccentEmission
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmModal
from craik.runtime.shell.textual_widgets.craik_input import (
    CraikInput,
    cli_prefix_warning,
    continue_multiline_value,
    should_continue_on_submit,
    slash_command_conversion,
)
from craik.runtime.shell.textual_widgets.footer_safe_area import FooterSafeArea
from craik.runtime.shell.textual_widgets.history_search import HistorySearchOverlay
from craik.runtime.shell.textual_widgets.run_activity_panel import (
    RunActivityPanel,
)
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.shell.textual_widgets.text_selection_hint import first_launch_selection_hint
from craik.runtime.shell.textual_widgets.theme_settings import (
    resolve_textual_theme as resolve_textual_theme,
)
from craik.runtime.shell.textual_widgets.theme_settings import (
    terminal_supports_textual as terminal_supports_textual,
)
from craik.runtime.shell.textual_widgets.toast_queue import ToastQueue
from craik.runtime.shell.textual_widgets.transcript_row_hint import TranscriptRowHint
from craik.runtime.shell.textual_widgets.transcript_search import TranscriptSearchOverlay
from craik.runtime.shell.textual_widgets.working_indicator import WorkingIndicator
from craik.runtime.status import auto_approve_status_payload

__all__ = ["CraikApp", "resolve_textual_theme", "run_textual_tui", "terminal_supports_textual"]


class CraikApp(CraikAppActivityMixin, CraikAppDispatchMixin, App[None]):
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
        self._active_claude_process: InterruptibleProcess | None = None
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

    def _dispatch_contract(self, text: str) -> CommandResult:
        """Dispatch slash text through the CLI/TUI contract layer."""
        return _contract_invoke(
            text,
            registry=self.registry,
            env=self.env,
            interactive_prompt_handler=self._open_modal_for_request,
        )

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
                mode=_active_permission_mode_display(self.env),
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
            self._toast("No interruptible audited run is active.", severity="information")

    def action_insert_newline(self) -> None:
        input_widget = self.query_one("#input", CraikInput)
        input_widget.value = continue_multiline_value(input_widget.value)
        input_widget.cursor_position = len(input_widget.value)

    def action_cycle_claude_permission_mode(self) -> None:
        # Vendor-aware Shift-Tab cycle: step through the ACTIVE vendor's real
        # mode set (Claude / Gemini / Codex), storing into that vendor's env var.
        spec = active_vendor_mode_spec(self.env)
        next_mode = spec.next_stored(self.env)
        self.env[spec.env_var] = next_mode
        label = _vendor_mode_display(spec.family, next_mode)
        self._toast(f"{spec.label} mode: {label}", severity="information")
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

def run_textual_tui(*, env: dict[str, str] | None = None) -> int:
    """Run the Textual app and return a process-style exit code."""
    app = CraikApp(env=env)
    result = app.run()
    return int(result or 0)
