from __future__ import annotations

import asyncio
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.session import BackendPromptResult
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.shell.textual_app import (
    CLAUDE_CODE_RUN_APPROVED_ENV,
    CLAUDE_PERMISSION_MODE_ENV,
    CraikApp,
    _claude_code_run_approval_request,
    _claude_progress_markup,
    _display_model_label,
    _model_transcript_markup,
    _user_transcript_markup,
    _uses_model_backed_slash_execution,
)
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmModal
from craik.runtime.shell.textual_widgets.craik_input import (
    CraikInput,
    cli_prefix_warning,
    collapse_paste_placeholder,
)
from craik.runtime.shell.textual_widgets.run_activity_panel import (
    RunActivityPanel,
    RunActivityState,
)
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.shell.textual_widgets.working_indicator import WorkingIndicator
from craik.runtime.shell.transcript_renderers import render_claude_run_summary


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def _gateway_payload(text: str) -> dict[str, object]:
    return {
        "schema": "craik.provider_backed_run_execution",
        "status": "completed",
        "run": {"id": "run_textual_gateway", "task_id": "task_textual_gateway"},
        "handoff": {"id": "handoff_textual_gateway"},
        "run_outputs": [{"observed_output": {"text": text}}],
        "receipt_ids": ["receipt_textual_gateway"],
    }


def test_textual_app_mounts_status_bar_and_welcome(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            assert "Craik" in pilot.app.query_one("#status", StatusBar).current_status

    asyncio.run(run())


def test_textual_app_shows_slash_popup(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            await pilot.press("/")
            assert pilot.app.query_one("#slash-popup").display

    asyncio.run(run())


def test_textual_model_prompt_shows_waiting_indicator(
    monkeypatch,
    tmp_path: Path,
) -> None:
    started = threading.Event()
    release = threading.Event()

    class _GatewayClient:
        def __init__(self, **kwargs: object) -> None:
            self.event_handler = kwargs["event_handler"]

        def submit_prompt(self, text: str) -> BackendPromptResult:
            started.set()
            assert text == "hello"
            event_handler = self.event_handler
            assert callable(event_handler)
            event_handler(
                BackendEvent(
                    type="model.selected",
                    data={"model": "openai/gpt-5.2"},
                )
            )
            assert release.wait(2)
            return BackendPromptResult(payload=_gateway_payload("model response"))

    monkeypatch.setattr("craik.runtime.shell.textual_app.GatewaySessionClient", _GatewayClient)

    async def run() -> None:
        app = CraikApp(env={**_env(tmp_path), "CRAIK_QUICK": "1"})
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "hello"
            await pilot.press("enter")
            assert started.wait(1)
            await pilot.pause(0.1)
            working = app.query_one("#working", WorkingIndicator)
            assert working.display
            assert not input_widget.disabled
            assert "Model thinking" in str(working.render())
            assert "Gateway selected" in str(app.query_one("#run-activity").render())
            release.set()
            for _ in range(20):
                await pilot.pause(0.05)
                if not working.display:
                    break
            assert not working.display
            assert not input_widget.disabled
            assert app._transcript_lines[-1] == "model response"

    asyncio.run(run())


def test_textual_active_run_queues_next_input(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    first_started = threading.Event()
    first_release = threading.Event()
    second_done = threading.Event()

    class _GatewayClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def submit_prompt(self, text: str) -> BackendPromptResult:
            calls.append(text)
            if text == "first":
                first_started.set()
                assert first_release.wait(2)
                return BackendPromptResult(payload=_gateway_payload("first response"))
            second_done.set()
            return BackendPromptResult(payload=_gateway_payload("second response"))

    monkeypatch.setattr("craik.runtime.shell.textual_app.GatewaySessionClient", _GatewayClient)

    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "first"
            await pilot.press("enter")
            assert first_started.wait(1)
            input_widget.value = "second"
            await pilot.press("enter")
            await pilot.pause(0.1)
            assert app._queued_inputs == ["second"]
            assert "1 queued" in input_widget.placeholder
            first_release.set()
            for _ in range(20):
                await pilot.pause(0.05)
                if second_done.is_set() and not app._model_prompt_active:
                    break
            assert second_done.is_set()
            assert calls == ["first", "second"]
            assert app._transcript_lines[-1] == "second response"

    asyncio.run(run())


def test_textual_run_claude_code_shows_waiting_indicator(
    tmp_path: Path,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def _dispatch_contract(self: CraikApp, text: str) -> CommandResult:
        from craik.runtime.shell.contract_runtime.builtin_slash_commands import (
            _emit_claude_code_progress,
        )

        started.set()
        assert text.startswith("/run --backend claude-code")
        _emit_claude_code_progress("Claude Code is using `Read`.")
        assert release.wait(2)
        return CommandResult(payload="done", shape="markdown", text="done", command_name="run")

    async def run() -> None:
        app = CraikApp(env={**_env(tmp_path), CLAUDE_CODE_RUN_APPROVED_ENV: "1"})
        app._dispatch_contract = _dispatch_contract.__get__(app, CraikApp)  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "/run --backend claude-code update docs"
            await pilot.press("enter")
            assert started.wait(1)
            await pilot.pause(0.1)
            working = app.query_one("#working", WorkingIndicator)
            assert working.display
            assert not input_widget.disabled
            release.set()
            for _ in range(20):
                await pilot.pause(0.05)
                if not working.display:
                    break
            assert not working.display
            assert not input_widget.disabled
            assert "Claude Code: Claude Code is using `Read`." in app._transcript_lines
            assert app._transcript_lines[-1] == "done"

    asyncio.run(run())


def test_textual_run_claude_code_requires_modal_approval(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()
    app_holder: list[CraikApp] = []

    def _dispatch_contract(self: CraikApp, text: str) -> CommandResult:
        assert app_holder[0].env[CLAUDE_CODE_RUN_APPROVED_ENV] == "1"
        started.set()
        assert release.wait(2)
        return CommandResult(payload="done", shape="markdown", text="done", command_name="run")

    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        app_holder.append(app)
        app._dispatch_contract = _dispatch_contract.__get__(app, CraikApp)  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "/run --backend claude-code update docs"
            await pilot.press("enter")
            assert isinstance(app.screen, ConfirmModal)
            assert not started.is_set()
            await pilot.click("#confirm-yes")
            assert started.wait(1)
            assert (
                "Claude Code run authority approved for this TUI dispatch."
                in app._transcript_lines
            )
            release.set()
            for _ in range(20):
                await pilot.pause(0.05)
                if CLAUDE_CODE_RUN_APPROVED_ENV not in app.env:
                    break
            assert CLAUDE_CODE_RUN_APPROVED_ENV not in app.env
            assert input_widget.value == ""

    asyncio.run(run())


def test_textual_anthropic_marker_prompt_streams_without_preapproval(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(
        AuthProfile(
            id="anthropic:default",
            kind=CredentialKind.MARKER,
            provider_family="anthropic",
            metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
            created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
            last_status="ok",
        )
    )
    monkeypatch.setattr(
        "craik.runtime.auth.login.claude_cli_runtime_status",
        lambda: CredentialStatus(status="ok"),
    )
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(
            [
                (
                    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                    '"name":"Read","input":{"file_path":"README.md"}}]}}\n'
                ),
                '{"type":"result","result":"from stream"}\n',
            ]
        )

        pid = 12345

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        assert "--output-format" in args
        assert "stream-json" in args
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    async def run() -> None:
        app = CraikApp(env=env)
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "/model set anthropic/claude-sonnet-4-20250514"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause(0.05)
                if "anthropic/claude-sonnet-4-20250514" in app.query_one(
                    "#status",
                    StatusBar,
                ).current_status:
                    break
            input_widget.value = "Review the docs"
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause(0.05)
                if not app._model_prompt_active:
                    break
            assert not isinstance(app.screen, ConfirmModal)
            assert any("Audited run" in line for line in app._transcript_lines)
            assert any("from stream" in line for line in app._transcript_lines)

    asyncio.run(run())


def test_claude_code_run_detection_accepts_equals_backend_form() -> None:
    assert _uses_model_backed_slash_execution("/run --backend claude-code update docs")
    assert _uses_model_backed_slash_execution("/run --backend=claude-code update docs")


def test_claude_code_approval_request_explains_permission_mode() -> None:
    request = _claude_code_run_approval_request(
        "/run --backend claude-code update docs",
        mode="Plan",
    )

    assert "Current mode: Plan" in request.message
    assert "preview intent without editing" in request.message


def test_textual_run_claude_code_full_path_approval_invokes_claude(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    calls: list[list[str]] = []
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(['{"type":"result","result":"docs updated"}\n'])

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        calls.append(list(args))
        assert kwargs["env"][CLAUDE_CODE_RUN_APPROVED_ENV] == "1"
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "/run --backend=claude-code update docs"
            await pilot.press("enter")
            assert isinstance(app.screen, ConfirmModal)
            await pilot.click("#confirm-yes")
            for _ in range(40):
                await pilot.pause(0.05)
                if calls and not app._model_prompt_active:
                    break
            assert calls
            assert any(
                "Claude Code run `run_update_docs`" in line
                for line in app._transcript_lines
            )
            assert CLAUDE_CODE_RUN_APPROVED_ENV not in app.env

    asyncio.run(run())


def test_textual_interrupt_run_terminates_active_claude_process(tmp_path: Path) -> None:
    class _Process:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test():
            process = _Process()
            app._prepare_active_claude_code_run()
            app._set_active_claude_process(process)  # type: ignore[arg-type]
            assert app._active_claude_cancel is not None
            app.action_interrupt_run()
            await asyncio.sleep(0)
            assert process.terminated
            assert app._active_claude_cancel.is_set()
            assert (
                "Claude Code: Interrupt requested. Stopping Claude Code..."
                in app._transcript_lines
            )

    asyncio.run(run())


def test_textual_model_set_refreshes_footer(tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "/model set anthropic/claude-opus-4-7"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause(0.05)
                status = app.query_one("#status", StatusBar).current_status
                if "anthropic/claude-opus-4-7" in status:
                    break
            assert "anthropic/claude-opus-4-7" in app.query_one(
                "#status",
                StatusBar,
            ).current_status

    asyncio.run(run())


def test_textual_transcript_distinguishes_user_and_model_text() -> None:
    user = _user_transcript_markup("hello [not markup]")
    model = _model_transcript_markup("answer https://example.com")
    rendered_user = _render_to_text(user)
    rendered_model = _render_to_text(model)

    assert isinstance(user, Panel)
    assert "You" in rendered_user
    assert "hello [not markup]" in rendered_user
    assert "Model" in rendered_model
    assert "https://example.com" in rendered_model


def test_model_transcript_title_uses_active_model_label() -> None:
    label = _display_model_label("anthropic/claude-opus-4-7")
    rendered = _render_to_text(_model_transcript_markup("answer", model_label=label))

    assert label == "Anthropic Claude Opus 4.7"
    assert "Anthropic Claude Opus 4.7" in rendered
    assert "answer" in rendered


def test_claude_progress_renders_diff_with_syntax() -> None:
    rendered = _render_to_text(
        _claude_progress_markup("--- a/docs/file.md\n+++ b/docs/file.md\n-old\n+new")
    )

    assert "Claude Code" in rendered
    assert "a/docs/file.md" in rendered
    assert "+new" in rendered


def test_claude_run_summary_surfaces_operator_artifacts() -> None:
    rendered = _render_to_text(
        render_claude_run_summary(
            {
                "schema": "craik.claude_code_run_execution",
                "status": "completed",
                "run": {"id": "run_docs", "task_id": "task_docs"},
                "handoff": {"id": "handoff_docs"},
                "receipt_ids": ["receipt_1", "receipt_2"],
                "run_outputs": [
                    {
                        "observed_output": {
                            "text": "Updated docs and ran checks.",
                            "activity": {
                                "tools": ["Read", "Edit", "Bash"],
                                "files": ["docs/terminal-ui.md"],
                                "commands": ["uv run pytest tests/test_v0122_textual_app.py"],
                            },
                        }
                    }
                ],
                "next_commands": ["/run inspect run_docs"],
            }
        )
    )

    assert "Claude Code run summary" in rendered
    assert "task_docs" in rendered
    assert "docs/terminal-ui.md" in rendered
    assert "uv run pytest tests/test_v0122_textual_app.py" in rendered
    assert "Updated docs and ran checks." in rendered


def test_run_activity_panel_explains_permission_mode() -> None:
    panel = RunActivityPanel()
    panel.update_activity(RunActivityState(backend="Claude Code", mode="Plan"))

    assert "Plan (preview only)" in str(panel.render())


def test_run_activity_panel_shows_recent_event_trail() -> None:
    panel = RunActivityPanel()
    panel.update_activity(
        RunActivityState(
            backend="Claude Code",
            recent_events=("Preparing run", "Created task", "Claude Code is using `Read`."),
        )
    )

    rendered = str(panel.render())

    assert "recent Preparing run" in rendered
    assert "Created task" in rendered
    assert "Claude Code is using" in rendered


def _render_to_text(renderable: object) -> str:
    console = Console(width=100, record=True, force_terminal=False)
    console.print(renderable)
    return console.export_text()


def test_shift_tab_cycles_claude_permission_mode(tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            await pilot.press("backtab")
            assert app.env[CLAUDE_PERMISSION_MODE_ENV] == "acceptEdits"
            assert "Claude Accept edits" in app.query_one("#status", StatusBar).current_status
            await pilot.press("backtab")
            assert app.env[CLAUDE_PERMISSION_MODE_ENV] == "plan"
            assert "Claude Plan" in app.query_one("#status", StatusBar).current_status

    asyncio.run(run())


def test_shift_tab_mode_binding_has_priority() -> None:
    binding = next(
        binding
        for binding in CraikApp.BINDINGS
        if getattr(binding, "action", None) == "cycle_claude_permission_mode"
    )

    assert getattr(binding, "priority", False) is True
    assert "backtab" in binding.key
    assert "shift+tab" in binding.key


def test_tui_does_not_bind_terminal_copy_shortcut() -> None:
    keys: list[str] = []
    for binding in CraikApp.BINDINGS:
        if isinstance(binding, tuple):
            key, action = binding[0], binding[1]
        else:
            key = getattr(binding, "key", "")
            action = getattr(binding, "action", None)
        if action == "copy_transcript":
            keys.append(key)

    assert keys == ["ctrl+y"]
    assert all("ctrl+shift+c" not in key for key in keys)
    assert not hasattr(CraikApp, "on_click")


def test_copy_command_copies_latest_response(
    monkeypatch,
    tmp_path: Path,
) -> None:
    copied: list[str] = []

    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        monkeypatch.setattr(app, "copy_to_clipboard", lambda text: copied.append(text))
        async with app.run_test() as pilot:
            app._write_transcript("[bold]rendered[/bold]", plain_text="rendered")
            app._write_transcript("latest response")
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "/copy"
            await pilot.press("enter")
            await pilot.pause(0.1)

    asyncio.run(run())

    assert copied
    assert copied[-1] == "latest response"


def test_copy_transcript_command_copies_plain_transcript(
    monkeypatch,
    tmp_path: Path,
) -> None:
    copied: list[str] = []

    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        monkeypatch.setattr(app, "copy_to_clipboard", lambda text: copied.append(text))
        async with app.run_test() as pilot:
            app._write_transcript("[bold]rendered[/bold]", plain_text="rendered")
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "/copy transcript"
            await pilot.press("enter")
            await pilot.pause(0.1)

    asyncio.run(run())

    assert copied
    assert copied[-1].endswith("rendered")
    assert "[bold]rendered[/bold]" not in copied[-1]


def test_copy_command_prefers_selected_transcript_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    copied: list[str] = []

    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        monkeypatch.setattr(app, "copy_to_clipboard", lambda text: copied.append(text))
        async with app.run_test():
            app._write_transcript("row 1")
            app._write_transcript("row 2")
            app._select_transcript_row(2, extend=False)
            app.action_copy_transcript()
            await asyncio.sleep(0)

    asyncio.run(run())

    assert copied == ["row 2"]


def test_cli_prefix_warning_preserves_command_intent() -> None:
    warning = cli_prefix_warning("craik auth login openai")

    assert warning is not None
    assert "`/auth`" in warning
    assert "Ctrl-D" in warning


def test_paste_collapse_threshold() -> None:
    assert collapse_paste_placeholder("one\ntwo") is None
    assert collapse_paste_placeholder("one\ntwo\nthree") == "[3 lines of text]"
