"""Single-entity card renderer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rich.markup import escape
from rich.panel import Panel
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


def render_card(
    payload: Mapping[str, Any] | None,
    *,
    title: str | None = None,
    next_actions: Sequence[NextAction] = (),
    empty_state_message: str | None = None,
) -> Panel:
    """Render one mapping payload as a compact detail card."""
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column()

    if not payload:
        table.add_row("empty", empty_state_message or "No values.")
        return Panel(table, title=title)

    actions_by_field = _actions_by_field(next_actions)
    for key, value in payload.items():
        field = str(key)
        rendered_value = _render_value(value)
        action = actions_by_field.get(field)
        if action is not None:
            rendered_value = f"{rendered_value}  ->  {escape(action.text)}"
        table.add_row(_label(field), rendered_value)
    return Panel(table, title=title)


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
    if isinstance(value, dict):
        return summarize_nested(value, item_name="keys")
    if isinstance(value, list):
        return summarize_nested(value, item_name="items")
    if value is None:
        return icon_for_status("missing")
    return escape(str(value))
