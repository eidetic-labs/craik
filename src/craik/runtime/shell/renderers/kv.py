"""Compact key-value renderer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rich.markup import escape
from rich.table import Table

from craik.runtime.contract.command_result import NextAction
from craik.runtime.shell.renderers.nested_summary import summarize_nested
from craik.runtime.shell.renderers.status_icons import icon_for_bool, icon_for_status

_STATUS_VALUES = {
    "active",
    "configured",
    "error",
    "fail",
    "failed",
    "false",
    "loading",
    "missing",
    "ok",
    "pending",
    "ready",
    "success",
    "true",
    "unconfigured",
    "unknown",
    "warn",
    "warning",
}


def render_kv(
    payload: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
    *,
    next_actions: Sequence[NextAction] = (),
    empty_state_message: str | None = None,
) -> Table:
    """Render a compact two-column key-value payload."""
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column()

    items = _payload_items(payload)
    if not items:
        table.add_row("empty", empty_state_message or "No values.")
        return table

    actions_by_field = _actions_by_field(next_actions)
    for key, value in items:
        rendered_value = _render_value(value)
        action = actions_by_field.get(key)
        if action is not None:
            rendered_value = f"{rendered_value}  ->  {escape(action.text)}"
        table.add_row(_label(key), rendered_value)
    return table


def _payload_items(
    payload: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
) -> list[tuple[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, Mapping):
        return [(str(key), value) for key, value in payload.items()]
    return [(str(key), value) for key, value in payload]


def _actions_by_field(next_actions: Sequence[NextAction]) -> dict[str, NextAction]:
    actions: dict[str, NextAction] = {}
    for action in next_actions:
        if action.field is not None:
            actions[action.field] = action
    return actions


def _label(key: str) -> str:
    return escape(key.replace("_", " "))


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return icon_for_bool(value)
    if isinstance(value, str):
        if value.lower() in _STATUS_VALUES:
            return f"{icon_for_status(value)} {escape(value)}"
        return escape(value)
    if value is None:
        return icon_for_status("missing")
    if isinstance(value, dict):
        return escape(summarize_nested(value, item_name="fields"))
    if isinstance(value, list):
        return escape(summarize_nested(value, item_name="items"))
    return escape(str(value))
