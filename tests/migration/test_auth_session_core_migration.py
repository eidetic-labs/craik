"""Migration coverage for core auth/session/model slash surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from craik.cli import app
from craik.runtime.auth.commands import auth_status_result, auth_summary_result
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result
from craik.runtime.model_commands import model_list_result, model_set_result, model_status_result
from craik.runtime.providers.commands import provider_list_result
from craik.runtime.session_commands import session_activate_result, session_shell_status_result
from craik.runtime.shell.slash_commands import dispatch_slash_command


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / "craik-home")}


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_auth_slash_uses_shared_payloads(tmp_path: Path) -> None:
    env = _env(tmp_path)

    auth = dispatch_slash_command("/auth", env=env)
    status = dispatch_slash_command("/auth status", env=env)

    assert json.loads(auth.text) == auth_summary_result(env).payload
    assert json.loads(status.text) == auth_status_result(env).payload


def test_auth_tui_snapshot(tmp_path: Path) -> None:
    env = _env(tmp_path)
    result = auth_summary_result(env)

    output = _capture(format_command_result(result, kind="tui"), width=80).replace(
        env["CRAIK_HOME"],
        "<craik-home>",
    )

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "auth"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))


def test_provider_and_model_slash_use_shared_payloads(tmp_path: Path) -> None:
    env = _env(tmp_path)

    model_set = dispatch_slash_command("/model set openai/gpt-4o-mini", env=env)
    model = dispatch_slash_command("/model", env=env)
    model_list = dispatch_slash_command("/model list", env=env)
    provider = dispatch_slash_command("/provider", env=env)

    assert model_set.text == "Active model set to `openai/gpt-4o-mini`."
    assert json.loads(model.text) == model_status_result(env).payload
    assert json.loads(model_list.text) == model_list_result(env).payload
    assert [
        item["id"] for item in json.loads(provider.text)
    ] == [item["id"] for item in provider_list_result().payload]


def test_sessions_slash_uses_shared_session_helpers(tmp_path: Path) -> None:
    env = _env(tmp_path)

    resume = dispatch_slash_command("/resume session_alpha", env=env)
    sessions = dispatch_slash_command("/sessions", env=env)

    assert resume.text == session_activate_result("session_alpha", env=env).text
    assert json.loads(sessions.text) == session_shell_status_result(env).payload


def test_sessions_tui_snapshot(tmp_path: Path) -> None:
    env = _env(tmp_path)
    result = session_shell_status_result(env)

    output = _capture(format_command_result(result, kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "sessions"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))


def test_core_auth_session_helpers_return_command_results(tmp_path: Path) -> None:
    env = _env(tmp_path)

    auth = auth_summary_result(env)
    model = model_set_result("openai/gpt-4o-mini", env=env)
    sessions = session_shell_status_result(env)

    assert isinstance(auth, CommandResult)
    assert isinstance(model, CommandResult)
    assert isinstance(sessions, CommandResult)
    assert sessions.payload["active_session"] is None


def test_core_auth_session_commands_are_registered() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/auth-list") is not None
    assert registry.spec_by_name("/auth-status") is not None
    assert registry.spec_by_name("/model") is not None
    assert registry.spec_by_name("/model-list") is not None
    assert registry.spec_by_name("/sessions") is not None
    assert registry.spec_by_name("/resume") is not None
