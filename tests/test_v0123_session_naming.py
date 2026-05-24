from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from craik.runtime.agents.session_naming import SessionNameError, validate_session_name
from craik.runtime.agents.sessions import start_agent_session
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


@pytest.mark.parametrize(
    "name",
    [
        "Desk review",
        "incident-42",
        "alpha_beta",
        "A" * 64,
    ],
)
def test_session_name_validation_accepts_operator_labels(name: str) -> None:
    assert validate_session_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        " leading",
        "trailing ",
        "A" * 65,
        "bad/name",
        "bad\nname",
    ],
)
def test_session_name_validation_rejects_ambiguous_labels(name: str) -> None:
    with pytest.raises(SessionNameError):
        validate_session_name(name)


def test_rename_slash_command_persists_shell_session_name(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = dispatch_slash_command("/rename Incident 42", env=env)
    sessions = dispatch_slash_command("/sessions", env=env)

    assert result.exit_code == 0
    assert env["CRAIK_SESSION_NAME"] == "Incident 42"
    assert json.loads(sessions.text)["shell_session_name"] == "Incident 42"


def test_rename_slash_command_rejects_invalid_name(tmp_path: Path) -> None:
    result = dispatch_slash_command("/rename bad/name", env=_env(tmp_path))

    assert result.exit_code == 2
    assert "invalid session name" in result.text


def test_agent_session_display_name_round_trips(tmp_path: Path) -> None:
    paths = ensure_craik_home(_env(tmp_path))
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        state = start_agent_session(
            store,
            session_id="agent_alpha",
            operator_subject="local-user:test",
            provider_id="openai",
            display_name="Planning desk",
        )
        stored = store.get_agent_session_state(state.id)
    finally:
        store.close()

    assert stored is not None
    assert stored.display_name == "Planning desk"


def test_textual_status_bar_renders_session_name(tmp_path: Path) -> None:
    async def run() -> None:
        env = _env(tmp_path)
        env["CRAIK_SESSION_NAME"] = "Desk review"
        async with CraikApp(env=env).run_test() as pilot:
            status = pilot.app.query_one("#status", StatusBar).current_status
            assert "Desk review" in status

    asyncio.run(run())
