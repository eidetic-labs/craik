"""Renderer pipeline entrypoint."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from craik.runtime.contract.command_result import NextAction, PayloadShape
from craik.runtime.shell.renderers.auto import detect_shape
from craik.runtime.shell.renderers.card import render_card
from craik.runtime.shell.renderers.card_list import render_card_list
from craik.runtime.shell.renderers.kv import render_kv
from craik.runtime.shell.renderers.markdown import render_markdown
from craik.runtime.shell.renderers.table import render_table
from craik.runtime.shell.renderers.tree import render_tree


def render(
    payload: Any,
    *,
    shape: PayloadShape = "auto",
    next_actions: Sequence[NextAction] = (),
    empty_state_message: str | None = None,
) -> object:
    """Render a structured payload using the requested or detected shape."""
    resolved_shape = detect_shape(payload) if shape == "auto" else shape
    if resolved_shape == "kv":
        return render_kv(
            payload if isinstance(payload, dict) else {"value": payload},
            next_actions=next_actions,
            empty_state_message=empty_state_message,
        )
    if resolved_shape == "card":
        return render_card(
            payload if isinstance(payload, dict) else {"value": payload},
            next_actions=next_actions,
            empty_state_message=empty_state_message,
        )
    if resolved_shape == "card_list":
        return render_card_list(
            payload if isinstance(payload, list) else [payload],
            next_actions=next_actions,
            empty_state_message=empty_state_message,
        )
    if resolved_shape == "table":
        return render_table(payload, empty_state_message=empty_state_message)
    if resolved_shape == "tree":
        return render_tree(payload, empty_state_message=empty_state_message)
    if resolved_shape == "markdown":
        return render_markdown(payload)
    return render_tree(payload, empty_state_message=empty_state_message)


__all__ = ["render"]
