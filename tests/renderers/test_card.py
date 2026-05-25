"""Tests for the single-entity card renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from craik.runtime.contract.command_result import NextAction
from craik.runtime.shell.renderers.card import render_card
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


def test_render_card_empty_payload() -> None:
    output = _capture(render_card({}, title="Provider", empty_state_message="No provider."))

    assert "Provider" in output
    assert "empty" in output
    assert "No provider." in output


def test_render_card_populated_payload() -> None:
    output = _capture(
        render_card(
            {
                "provider": "openai",
                "configured": True,
                "status": "ready",
            },
            title="Provider",
        )
    )

    assert "Provider" in output
    assert "provider" in output
    assert "openai" in output
    assert STATUS_OK in output


def test_render_card_collapses_nested_fields() -> None:
    output = _capture(
        render_card(
            {
                "capabilities": {
                    "chat": True,
                    "tools": True,
                    "vision": True,
                    "images": True,
                },
                "models": ["gpt-4o", "gpt-4o-mini", "o3"],
            }
        )
    )

    assert "capabilities" in output
    assert "4 keys" in output
    assert "models" in output
    assert "3 items" in output


def test_render_card_field_next_action_is_inline() -> None:
    output = _capture(
        render_card(
            {"provider_configured": False},
            next_actions=[
                NextAction(
                    text="run /auth login openai",
                    command="/auth login",
                    field="provider_configured",
                )
            ],
        )
    )

    assert "provider configured" in output
    assert STATUS_FAIL in output
    assert "run /auth login openai" in output


def test_render_card_respects_narrow_width() -> None:
    output = _capture(
        render_card({"status": "configured"}, title="Narrow"),
        width=40,
    )

    assert "Narrow" in output
    assert "configured" in output
