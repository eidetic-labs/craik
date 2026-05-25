"""Tests for the compact tree renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from craik.runtime.shell.renderers.status_icons import STATUS_OK
from craik.runtime.shell.renderers.tree import render_tree


def _capture(renderable: Any) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=80)
    console.print(renderable)
    return console.export_text()


def test_render_tree_empty_payload() -> None:
    output = _capture(render_tree({}, empty_state_message="No values."))

    assert "No values." in output


def test_render_tree_compacts_scalar_leaf() -> None:
    output = _capture(render_tree({"state": "ready", "configured": True}))

    assert "state: ready" in output
    assert f"configured: {STATUS_OK}" in output


def test_render_tree_nested_payload() -> None:
    output = _capture(render_tree({"provider": {"name": "openai", "ready": True}}))

    assert "provider" in output
    assert "name: openai" in output
    assert f"ready: {STATUS_OK}" in output
