"""Tests for the CommandResult to SlashCommandResult adapter."""

from __future__ import annotations

from craik.runtime.contract.command_result import CommandResult
from craik.runtime.shell.contract_runtime.result_adapter import to_slash_command_result


def test_basic_shape_adaptation() -> None:
    result = CommandResult(payload={"a": 1}, shape="kv", text="a=1", exit_code=0)

    adapted = to_slash_command_result(result)

    assert adapted.payload_shape == "kv"
    assert adapted.payload == {"a": 1}
    assert adapted.text == "a=1"
    assert adapted.exit_code == 0


def test_exit_shell_adaptation() -> None:
    result = CommandResult(payload="bye", shape="markdown", text="bye", exit_shell=True)

    adapted = to_slash_command_result(result)

    assert adapted.exit_shell is True
