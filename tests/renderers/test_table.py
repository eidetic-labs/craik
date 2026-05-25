"""Tests for the table renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from craik.runtime.shell.renderers.status_icons import STATUS_OK
from craik.runtime.shell.renderers.table import render_table


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def test_render_table_empty_payload() -> None:
    output = _capture(render_table([], empty_state_message="No rows."))

    assert "No rows." in output


def test_render_table_flat_rows() -> None:
    output = _capture(render_table([{"provider": "openai", "configured": True}]))

    assert "provider" in output
    assert "openai" in output
    assert STATUS_OK in output


def test_render_table_collapses_nested_cells() -> None:
    output = _capture(
        render_table(
            [
                {
                    "provider": "openai",
                    "capabilities": {"chat": True, "tools": True, "vision": True},
                }
            ]
        )
    )

    assert "capabilities" in output
    assert "3 keys" in output


def test_render_table_drops_columns_when_too_narrow() -> None:
    row = {f"column_{index}": index for index in range(10)}
    output = _capture(render_table([row], terminal_width=40), width=40)

    assert "column" in output
    assert "0" in output
    assert "column 9" not in output
