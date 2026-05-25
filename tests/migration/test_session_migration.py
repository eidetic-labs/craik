"""Migration coverage for persistent session command contract surfaces."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import AgentSessionState
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result
from craik.runtime.paths import ensure_craik_home
from craik.runtime.session_commands import (
    session_activate_result,
    session_list_result,
    session_resume_result,
)
from craik.runtime.store import LocalStore

runner = CliRunner()


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_session_cli_and_slash_share_session_list(tmp_path: Path) -> None:
    env = _seed_session(tmp_path)

    cli = runner.invoke(app, ["session", "list"], env=env)
    slash = runner.invoke(app, ["slash", "/sessions"], env=env)

    assert cli.exit_code == 0, cli.output
    assert slash.exit_code == 0, slash.output
    assert json.loads(cli.stdout)[0]["id"] == json.loads(slash.stdout)["sessions"][0]["id"]


def test_session_commands_return_command_result_contract(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    env = _seed_session(tmp_path)
    monkeypatch.setenv("CRAIK_HOME", env["CRAIK_HOME"])

    listing = session_list_result()
    resume = session_resume_result("agent_session_docs")

    assert isinstance(listing, CommandResult)
    assert listing.shape == "card_list"
    assert resume.payload["resume_supported"] is True


def test_session_commands_are_registered_as_derived_slash_commands() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/sessions") is not None
    assert registry.spec_by_name("/session-show") is not None
    assert registry.spec_by_name("/resume") is not None
    assert registry.spec_by_name("/session-rename") is not None
    assert registry.spec_by_name("/session-export") is not None
    assert registry.spec_by_name("/session-prune") is not None
    assert registry.spec_by_name("/session-delete") is not None


def test_session_tui_snapshot(tmp_path: Path, monkeypatch: Any) -> None:
    env = _seed_session(tmp_path)
    monkeypatch.setenv("CRAIK_HOME", env["CRAIK_HOME"])
    result = session_resume_result("agent_session_docs")

    output = _capture(format_command_result(result, kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "session"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))


def test_resume_tui_snapshot(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "craik-home")}
    result = session_activate_result("session_alpha", env=env)

    output = _capture(format_command_result(result, kind="tui"), width=80)

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "resume"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))


def _seed_session(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    ensure_craik_home(env)
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator:test",
            email="operator@example.test",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime(2026, 5, 22, 13, 0, tzinfo=UTC),
        )
    )
    store = LocalStore.from_paths(ensure_craik_home(env))
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    try:
        store.initialize()
        store.put_agent_session_state(
            AgentSessionState(
                id="agent_session_docs",
                project_id="project_docs",
                operator_subject="operator:test",
                provider_id="openai",
                model_id="gpt-5",
                mode="interactive",
                status="idle",
                started_at=now,
                last_activity_at=now,
                updated_at=now,
            )
        )
    finally:
        store.close()
    return env
