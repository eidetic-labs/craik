"""Tests for the renderer dispatch entrypoint."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from craik.runtime.contract.command_result import NextAction
from craik.runtime.shell.renderers import render


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(
        color_system=None,
        force_terminal=False,
        record=True,
        width=width,
    )
    console.print(renderable)
    return console.export_text()


def test_render_dispatches_kv() -> None:
    output = _capture(render({"state": "ready"}, shape="kv"))

    assert "state" in output
    assert "ready" in output


def test_render_dispatches_auto_table() -> None:
    output = _capture(render([{"name": "openai"}, {"name": "anthropic"}]))

    assert "name" in output
    assert "openai" in output
    assert "anthropic" in output


def test_render_dispatches_card_list_with_next_action() -> None:
    output = _capture(
        render(
            [{"name": "openai", "configured": False}],
            shape="card_list",
            next_actions=[
                NextAction(
                    text="run /auth login openai",
                    command="/auth login",
                    field="configured",
                )
            ],
        )
    )

    assert "run /auth login openai" in output
