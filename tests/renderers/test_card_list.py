"""Tests for the list-of-cards renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from craik.runtime.contract.command_result import NextAction
from craik.runtime.shell.renderers.card_list import render_card_list
from craik.runtime.shell.renderers.status_icons import STATUS_FAIL, STATUS_OK


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(
        color_system=None,
        force_terminal=False,
        record=True,
        width=width,
    )
    console.print(renderable)
    return console.export_text()


def test_render_card_list_empty_payload() -> None:
    output = _capture(render_card_list([], empty_state_message="No providers."))

    assert "empty" in output
    assert "No providers." in output


def test_render_card_list_populated_payload() -> None:
    output = _capture(
        render_card_list(
            [
                {"name": "openai", "configured": True},
                {"name": "anthropic", "configured": False},
            ]
        )
    )

    assert "openai" in output
    assert "anthropic" in output
    assert STATUS_OK in output
    assert STATUS_FAIL in output


def test_render_card_list_collapses_nested_fields() -> None:
    output = _capture(
        render_card_list(
            [
                {
                    "name": "openai",
                    "capabilities": {"chat": True, "tools": True, "vision": True},
                }
            ]
        )
    )

    assert "capabilities" in output
    assert "3 keys" in output


def test_render_card_list_non_mapping_rows_become_value_cards() -> None:
    output = _capture(render_card_list(["one", "two"]))

    assert "Item 1" in output
    assert "one" in output
    assert "Item 2" in output
    assert "two" in output


def test_render_card_list_field_next_action_is_inline() -> None:
    output = _capture(
        render_card_list(
            [{"name": "openai", "configured": False}],
            next_actions=[
                NextAction(
                    text="run /auth login openai",
                    command="/auth login",
                    field="configured",
                )
            ],
        )
    )

    assert "configured" in output
    assert "run /auth login openai" in output
