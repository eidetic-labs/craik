"""Tests for the CommandResult contract type."""

from __future__ import annotations

import pytest

from craik.runtime.contract.command_result import (
    CommandResult,
    NextAction,
    PayloadShape,
)


def test_command_result_minimal_construction() -> None:
    result = CommandResult(payload={"key": "value"})

    assert result.payload == {"key": "value"}
    assert result.shape == "auto"
    assert result.exit_code == 0
    assert result.next_actions == []
    assert result.text is None
    assert result.empty_state_message is None


def test_command_result_full_construction() -> None:
    action = NextAction(
        text="run /auth login",
        command="/auth login",
        field="provider configured",
    )
    result = CommandResult(
        payload={"state": "unconfigured"},
        shape="kv",
        text="state: unconfigured",
        exit_code=1,
        next_actions=[action],
        empty_state_message="No providers configured yet.",
    )

    assert result.shape == "kv"
    assert result.next_actions[0].field == "provider configured"


def test_payload_shape_enum_values() -> None:
    legal: list[PayloadShape] = [
        "auto",
        "kv",
        "card",
        "card_list",
        "table",
        "tree",
        "markdown",
    ]

    for shape in legal:
        result = CommandResult(payload={}, shape=shape)
        assert result.shape == shape


def test_next_action_minimal() -> None:
    action = NextAction(text="run /clear", command="/clear")

    assert action.field is None


def test_command_result_is_frozen() -> None:
    result = CommandResult(payload={})

    with pytest.raises((AttributeError, TypeError)):
        result.payload = {"new": "value"}  # type: ignore[misc]
