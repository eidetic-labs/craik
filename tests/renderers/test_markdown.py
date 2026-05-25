"""Tests for the markdown renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from craik.runtime.shell.renderers.markdown import render_markdown


def _capture(renderable: Any) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=80)
    console.print(renderable)
    return console.export_text()


def test_render_markdown_heading() -> None:
    output = _capture(render_markdown("# Setup"))

    assert "Setup" in output
