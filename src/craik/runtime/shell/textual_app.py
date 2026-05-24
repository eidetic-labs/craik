"""Textual application for Craik's canonical interactive terminal runtime."""

from __future__ import annotations

import os
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import OptionList, RichLog

from craik import __version__
from craik.runtime.shell.external_editor import edit_text_externally
from craik.runtime.shell.readiness import ReadinessReport
from craik.runtime.shell.shell_history import append_history
from craik.runtime.shell.shell_invocation import (
    is_shell_invocation_text,
    run_shell_invocation,
)
from craik.runtime.shell.slash_commands import (
    SlashCommandResult,
    auto_approve_status_payload,
    dispatch_slash_command,
)
from craik.runtime.shell.slash_completer import complete_slash_input
from craik.runtime.shell.textual_modals import (
    ApprovalDecisionModal,
    AuthCaptureModal,
    AuthLogoutModal,
    ModalFlowResult,
)
from craik.runtime.shell.textual_widgets.accent_emission import AccentEmission
from craik.runtime.shell.textual_widgets.craik_input import (
    CraikInput,
    cli_prefix_warning,
    continue_multiline_value,
    should_continue_on_submit,
)
from craik.runtime.shell.textual_widgets.footer_safe_area import FooterSafeArea
from craik.runtime.shell.textual_widgets.history_search import HistorySearchOverlay
from craik.runtime.shell.textual_widgets.inline_link import linkify_text
from craik.runtime.shell.textual_widgets.slash_renderers import write_slash_command_result
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.shell.textual_widgets.theme_settings import configured_theme
from craik.runtime.shell.textual_widgets.working_indicator import WorkingIndicator
from craik.runtime.shell.tui import dispatch_tui_input


class CraikApp(App[None]):
    """Chat-first terminal UI with transcript, input, and bottom status bar."""

    CSS_PATH = "textual_app_dark.tcss"
    BINDINGS = [
        ("ctrl+d", "quit", "Exit"),
        ("ctrl+r", "history_search", "History"),
        ("ctrl+g", "external_editor", "Editor"),
        ("ctrl+x", "external_editor_prefix", "Editor Prefix"),
        ("shift+enter", "insert_newline", "Newline"),
        ("ctrl+j", "insert_newline", "Newline"),
        ("alt+enter", "insert_newline", "Newline"),
        ("escape", "hide_popup", "Dismiss"),
    ]

    readiness: reactive[ReadinessReport | None] = reactive(None)

    def __init__(self, *, env: dict[str, str] | None = None) -> None:
        super().__init__()
        self.env = dict(os.environ) if env is None else dict(env)
        self._editor_prefix_pending = False

    def compose(self) -> ComposeResult:
        yield RichLog(id="transcript", markup=True, wrap=True)
        with Container(id="slash-popup"):
            yield OptionList(id="slash-options")
        yield HistorySearchOverlay(env=self.env, id="history-search")
        yield WorkingIndicator("", id="working")
        yield CraikInput(placeholder="Type a prompt or /help", id="input")
        yield AccentEmission("", id="accent-emission")
        yield StatusBar(id="status", classes="status-bar")
        yield FooterSafeArea("", id="footer-safe-area")

    def on_mount(self) -> None:
        from craik.runtime.shell.readiness import resolve_readiness

        report = resolve_readiness(self.env)
        self.readiness = report
        transcript = self.query_one("#transcript", RichLog)
        mode = "audited" if report.operator_required else "single-operator"
        transcript.write(f"Welcome to Craik {__version__}. Mode: {mode}. Type a prompt or /help.")
        self.query_one("#status", StatusBar).update_status(
            report,
            cwd=Path.cwd(),
            auto_approve=auto_approve_status_payload(self.env) is not None,
            session_name=self.env.get("CRAIK_SESSION_NAME"),
        )
        self.query_one("#slash-popup", Container).display = False
        self.query_one("#history-search", HistorySearchOverlay).display = False
        self.query_one("#working", WorkingIndicator).display = False
        if auto_approve_status_payload(self.env) is not None:
            self._flash_accent("state")
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
        self._submit_text(event.value)

    def _submit_text(self, value: str) -> None:
        text = value.strip()
        input_widget = self.query_one("#input", CraikInput)
        if not text:
            return
        warning = cli_prefix_warning(text)
        if warning is not None:
            self.notify(warning, severity="warning", timeout=8)
            return
        transcript = self.query_one("#transcript", RichLog)
        transcript.write(f"> {text}")
        append_history(text, env=self.env)
        if is_shell_invocation_text(text):
            try:
                shell_result = run_shell_invocation(text, env=self.env, cwd=Path.cwd())
            except ValueError as error:
                transcript.write(str(error))
            else:
                transcript.write(shell_result.transcript_text)
                self._flash_accent("receipt")
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        if self._open_modal_flow(text):
            input_widget.value = ""
            self.query_one("#slash-popup", Container).display = False
            return
        result = self._dispatch(text)
        if text.startswith("/"):
            write_slash_command_result(transcript, result)
        else:
            transcript.write(linkify_text(result.text))
        input_widget.value = ""
        self.query_one("#slash-popup", Container).display = False
        if result.exit_shell:
            self.exit()

    def on_key(self, event: events.Key) -> None:
        if self._editor_prefix_pending:
            self._editor_prefix_pending = False
            if event.key == "ctrl+e":
                self.action_external_editor()
                event.stop()
                return
        overlay = self.query_one("#history-search", HistorySearchOverlay)
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

    def action_history_search(self) -> None:
        overlay = self.query_one("#history-search", HistorySearchOverlay)
        if overlay.display:
            overlay.move(1)
            return
        overlay.open()

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

    def action_insert_newline(self) -> None:
        input_widget = self.query_one("#input", CraikInput)
        input_widget.value = continue_multiline_value(input_widget.value)
        input_widget.cursor_position = len(input_widget.value)

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
            result = dispatch_slash_command(text, env=self.env)
        else:
            result = dispatch_tui_input(text, env=self.env)
        if text.startswith("/rename") or text.startswith("/theme"):
            self._refresh_status_bar()
            self._flash_accent("state")
        return result

    def _flash_accent(self, kind: str) -> None:
        self.query_one("#accent-emission", AccentEmission).flash(kind)

    def _refresh_status_bar(self) -> None:
        report = self.readiness
        if report is None:
            return
        self.query_one("#status", StatusBar).update_status(
            report,
            cwd=Path.cwd(),
            auto_approve=auto_approve_status_payload(self.env) is not None,
            session_name=self.env.get("CRAIK_SESSION_NAME"),
        )

    def _open_modal_flow(self, text: str) -> bool:
        tokens = text.split()
        if not tokens:
            return False
        if tokens[:2] in (["/auth", "login"], ["/provider", "login"]):
            provider = tokens[2] if len(tokens) > 2 else "openai"
            self.push_screen(AuthCaptureModal(provider, env=self.env), self._modal_complete)
            return True
        if tokens[:2] == ["/auth", "logout"]:
            profile = tokens[2] if len(tokens) > 2 else self._active_profile()
            self.push_screen(AuthLogoutModal(profile, env=self.env), self._modal_complete)
            return True
        if len(tokens) >= 3 and tokens[:2] == ["/approvals", "decide"]:
            self.push_screen(
                ApprovalDecisionModal(tokens[2], env=self.env),
                self._modal_complete,
            )
            return True
        return False

    def _modal_complete(self, result: ModalFlowResult | None) -> None:
        if result is None:
            return
        transcript = self.query_one("#transcript", RichLog)
        transcript.write(linkify_text(result.message))
        if result.severity != "information":
            self.notify(result.message, severity=result.severity, timeout=8)

    def _active_profile(self) -> str:
        report = self.readiness
        if report is not None:
            return report.active_profile
        return "openai:default"

    def _show_slash_popup(self, prefix: str) -> None:
        popup = self.query_one("#slash-popup", Container)
        options = self.query_one("#slash-options", OptionList)
        options.clear_options()
        for candidate in complete_slash_input(prefix, env=self.env)[:12]:
            label = candidate.value
            if candidate.description:
                label = f"{candidate.value}  {candidate.description}"
            options.add_option(label)
        popup.display = True


def resolve_textual_theme(env: dict[str, str] | None = None) -> str:
    """Resolve dark, light, or monochrome theme from env hints."""
    values = dict(os.environ) if env is None else env
    override = values.get("CRAIK_THEME", "").strip().lower()
    if override in {"dark", "light", "monochrome"}:
        return override
    if values.get("NO_COLOR") == "1":
        return "monochrome"
    stored = configured_theme(values)
    if stored is not None:
        return stored
    colorfgbg = values.get("COLORFGBG", "")
    if ";" in colorfgbg:
        try:
            background = int(colorfgbg.rsplit(";", 1)[1])
        except ValueError:
            return "dark"
        return "light" if background >= 7 else "dark"
    return "dark"


def terminal_supports_textual(env: dict[str, str] | None = None) -> bool:
    """Return whether the current terminal should launch the Textual UI."""
    values = dict(os.environ) if env is None else env
    if values.get("CRAIK_NO_TUI") == "1":
        return False
    if values.get("TERM") == "dumb":
        return False
    return True


def run_textual_tui(*, env: dict[str, str] | None = None) -> int:
    """Run the Textual app and return a process-style exit code."""
    app = CraikApp(env=env)
    result = app.run()
    return int(result or 0)
