"""Tests for CommandResult output format selection."""

from __future__ import annotations

import json
import sys

import pytest

from craik.runtime.contract.command_result import CommandResult, NextAction
from craik.runtime.contract.format import (
    detect_default_format,
    format_command_result,
)


def test_detect_default_format_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    assert detect_default_format() == "text"


def test_detect_default_format_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    assert detect_default_format() == "json"


def test_format_json_round_trips_payload() -> None:
    result = CommandResult(payload={"key": "value", "nested": {"k": 1}})
    output = format_command_result(result, kind="json")
    parsed = json.loads(output)

    assert parsed["payload"] == {"key": "value", "nested": {"k": 1}}
    assert parsed["shape"] == "auto"
    assert parsed["exit_code"] == 0


def test_format_json_includes_next_actions() -> None:
    result = CommandResult(
        payload={},
        next_actions=[
            NextAction(
                text="run /auth login",
                command="/auth login",
                field="provider configured",
            )
        ],
    )
    parsed = json.loads(format_command_result(result, kind="json"))

    assert parsed["next_actions"] == [
        {
            "text": "run /auth login",
            "command": "/auth login",
            "field": "provider configured",
        }
    ]


def test_format_text_includes_next_actions() -> None:
    result = CommandResult(
        payload={"state": "unconfigured"},
        text="Setup is incomplete.",
        next_actions=[NextAction(text="run /auth login", command="/auth login")],
    )
    output = format_command_result(result, kind="text")

    assert "Setup is incomplete." in output
    assert "/auth login" in output


def test_format_text_uses_empty_state_when_payload_absent() -> None:
    result = CommandResult(payload=None, empty_state_message="No results found.")

    assert format_command_result(result, kind="text") == "No results found."


@pytest.mark.xfail(reason="renderer pipeline lands in v0.12.8 Task 1.5+")
def test_format_tui_returns_rich_renderable() -> None:
    result = CommandResult(payload={"a": 1}, shape="kv")
    rendered = format_command_result(result, kind="tui")

    assert rendered is not None
