"""Tests for the compact key-value renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from craik.runtime.contract.command_result import NextAction
from craik.runtime.shell.renderers.kv import render_kv
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


def test_render_kv_empty_payload() -> None:
    output = _capture(render_kv({}, empty_state_message="No setup data."))

    assert "empty" in output
    assert "No setup data." in output


def test_render_kv_flat_payload() -> None:
    output = _capture(
        render_kv(
            {
                "state": "configured",
                "home": "/tmp/craik",
                "initialized": True,
            }
        )
    )

    assert "state" in output
    assert "configured" in output
    assert "home" in output
    assert "/tmp/craik" in output
    assert STATUS_OK in output


def test_render_kv_boolean_false_uses_fail_icon() -> None:
    output = _capture(render_kv({"operator_authenticated": False}))

    assert "operator authenticated" in output
    assert STATUS_FAIL in output


def test_render_kv_field_next_action_is_inline() -> None:
    output = _capture(
        render_kv(
            {"provider_configured": False},
            next_actions=[
                NextAction(
                    text="run /auth login <provider>",
                    command="/auth login",
                    field="provider_configured",
                )
            ],
        )
    )

    assert "provider configured" in output
    assert "run /auth login <provider>" in output


def test_render_kv_respects_terminal_width() -> None:
    output = _capture(
        render_kv({"provider_configured": False}),
        width=40,
    )

    assert "provider configured" in output
