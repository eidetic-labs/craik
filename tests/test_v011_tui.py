from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import AgentSessionState
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.tui import (
    MultilineComposer,
    build_tui_snapshot,
    complete_tui_command,
    dispatch_tui_input,
    render_approval_modal,
    render_tui_snapshot,
    run_tui,
)
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_tui_starts_without_config_and_renders_nonblank(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    result = runner.invoke(app, ["tui"], env=env)
    root_result = runner.invoke(app, ["--tui"], env=env)

    assert result.exit_code == 0
    assert root_result.exit_code == 0
    assert "Craik TUI" in result.output
    assert "Provider/Auth Status" in result.output
    assert "State: unconfigured" in result.output
    assert "Redaction: on" in result.output
    assert "Craik TUI" in root_result.output


def test_tui_fixture_mode_status_and_store_panels(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home), "CRAIK_FIXTURE": "1"}
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    try:
        store.initialize()
        store.put_agent_session_state(
            AgentSessionState(
                id="agent_session_tui",
                project_id="project_tui",
                operator_subject="operator:test",
                provider_id="fixture",
                model_id="fixture-model",
                mode="interactive",
                status="idle",
                started_at=now,
                last_activity_at=now,
                updated_at=now,
            )
        )
    finally:
        store.close()

    rendered = render_tui_snapshot(build_tui_snapshot(env))

    assert "State: fixture" in rendered
    assert "Sessions: 1" in rendered
    assert "Session Picker" in rendered
    assert "Gateway" in rendered


def test_tui_dispatches_shared_slash_commands(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    status = dispatch_tui_input("/status", env=env)
    model_help = dispatch_tui_input("/help model", env=env)

    assert json.loads(status.text)["state"] == "unconfigured"
    assert "Usage: /model" in model_help.text


def test_tui_autocomplete_and_multiline_composer() -> None:
    composer = MultilineComposer()

    assert complete_tui_command("/sta") == ["/status"]
    assert composer.accept("/compose") == (True, None)
    assert composer.accept("line one") == (True, None)
    assert composer.accept("line two") == (True, None)
    assert composer.accept(".") == (True, "line one\nline two")


def test_tui_approval_modal_redacts_secret_like_targets() -> None:
    rendered = render_approval_modal(
        approval_id="approval_docs",
        capability="model.chat",
        target="https://sk-live-secret-token@example.invalid",
        risk="provider call",
        policy="strict",
    )

    assert "Approval" in rendered
    assert "Retry: retry the blocked command after approval" in rendered
    assert "sk-live-secret-token" not in rendered
    assert "[REDACTED]" in rendered


def test_tui_scripted_input_streams_and_exits(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    output: list[str] = []

    exit_code = run_tui(
        env=env,
        output_func=output.append,
        stdin_isatty=True,
        lines=["/help status", "hello", "/exit"],
    )

    assert exit_code == 0
    assert any("Craik TUI" in item for item in output)
    assert any("Usage: /status" in item for item in output)
    assert any("Streaming output" in item for item in output)
    assert output[-1] == "Session ended."
