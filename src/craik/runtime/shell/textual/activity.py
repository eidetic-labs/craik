"""Transcript, queue, and activity methods for the Textual TUI app."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from rich.markup import escape
from textual.containers import Container
from textual.widgets import OptionList, RichLog

from craik.runtime.backend.claude_code import CLAUDE_CODE_RUN_APPROVED_ENV
from craik.runtime.shell.confirmations import record_confirmation_decision
from craik.runtime.shell.inline_actions import handle_inline_action
from craik.runtime.shell.modals.textual_flow import open_textual_modal_flow
from craik.runtime.shell.slash_completer import complete_slash_input
from craik.runtime.shell.textual.support import (
    _activity_details,
    _claude_permission_mode_label,
    _data_string,
    _data_string_list,
    _display_model_label,
    _gateway_event_message,
    _gateway_model_label,
    _latest_copyable_transcript_line,
    _non_response_transcript_line,
    _requires_claude_code_run_approval,
)
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmationRequest
from craik.runtime.shell.textual_widgets.craik_input import CraikInput
from craik.runtime.shell.textual_widgets.inline_action_table import InlineActionTable
from craik.runtime.shell.textual_widgets.run_activity_panel import (
    RunActivityPanel,
    RunActivityState,
)
from craik.runtime.shell.textual_widgets.transcript_row_hint import TranscriptRowHint


class CraikAppActivityMixin:
    env: dict[str, str]
    registry: Any
    readiness: Any
    _transcript_lines: list[str]
    _last_copyable_output: str | None
    _claude_code_approval_inflight: bool
    _selection_anchor: int | None
    _selected_transcript_rows: set[int]
    _queued_inputs: list[str]
    _model_prompt_active: bool
    _working_started_at: float | None
    _run_backend_label: str | None
    _last_run_event: str | None
    _current_run_tool: str | None
    _current_run_target: str | None
    _current_run_phase: str | None
    _current_run_id: str | None
    _current_task_id: str | None
    _run_files: list[str]
    _run_commands: list[str]
    _run_recent_events: list[str]
    _run_approvals: int
    _run_denials: int

    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...

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
            return str(report.active_profile)
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
