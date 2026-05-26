"""End-to-end smoke tests for TUI contract dispatch consumption."""

from __future__ import annotations

import os

import pytest


def test_textual_app_slash_command_routes_through_contract_dispatcher(tmp_path) -> None:
    pytest.importorskip("textual")
    from craik.runtime.contract import dispatch as contract_dispatch
    from craik.runtime.shell.textual_app import CraikApp

    baseline = contract_dispatch.get_invocation_count()

    app = CraikApp(env={"CRAIK_HOME": str(tmp_path / "home")})
    result = app._dispatch("/help")  # noqa: SLF001

    assert contract_dispatch.get_invocation_count() == baseline + 1
    assert "slash" in result.text.lower()


def test_tui_runner_slash_command_routes_through_contract_dispatcher(tmp_path) -> None:
    from craik.runtime.contract import dispatch as contract_dispatch
    from craik.runtime.shell.tui import dispatch_tui_input

    baseline = contract_dispatch.get_invocation_count()

    result = dispatch_tui_input("/help", env={"CRAIK_HOME": str(tmp_path / "home")})

    assert contract_dispatch.get_invocation_count() == baseline + 1
    assert "slash" in result.text.lower()


def test_agent_shell_routes_slash_commands_through_contract_dispatcher(tmp_path) -> None:
    from craik.runtime.contract import dispatch as contract_dispatch
    from craik.runtime.shell.agent_shell import run_shell

    baseline = contract_dispatch.get_invocation_count()
    output: list[str] = []

    exit_code = run_shell(
        env={"CRAIK_HOME": str(tmp_path / "home"), **os.environ},
        stdin_isatty=True,
        lines=["/help"],
        output_func=output.append,
    )

    assert exit_code == 0
    assert contract_dispatch.get_invocation_count() == baseline + 1
    assert any("slash" in item.lower() for item in output)
