"""Column-budgeted table renderer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rich.markup import escape
from rich.table import Table

from craik.runtime.shell.renderers.nested_summary import summarize_nested
from craik.runtime.shell.renderers.status_icons import icon_for_bool, icon_for_status
from craik.runtime.shell.renderers.width_budget import budget_columns, truncate_to_width

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


def render_table(
    payload: Any,
    *,
    terminal_width: int = 80,
    empty_state_message: str | None = None,
) -> Table:
    """Render a payload as a width-budgeted table."""
    rows = _rows(payload)
    table = Table(show_header=True, expand=False)
    if not rows:
        table.add_column("result")
        table.add_row(empty_state_message or "No rows.")
        return table

    columns = _columns(rows)
    widths = budget_columns(
        num_columns=len(columns),
        terminal_width=terminal_width,
        min_width=8,
    )
    visible_columns = columns[: len(widths)]
    for column, width in zip(visible_columns, widths, strict=True):
        table.add_column(column.replace("_", " "), width=width, overflow="ellipsis")
    for row in rows:
        table.add_row(
            *[
                _cell(row.get(column), width=widths[index])
                for index, column in enumerate(visible_columns)
            ]
        )
    return table


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) if isinstance(row, Mapping) else {"value": row} for row in payload]
    if isinstance(payload, Mapping):
        return [dict(payload)]
    if payload is None:
        return []
    return [{"value": payload}]


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _cell(value: Any, *, width: int) -> str:
    if isinstance(value, bool):
        return icon_for_bool(value)
    if isinstance(value, str):
        rendered = f"{icon_for_status(value)} {value}" if value.lower() in _STATUS_VALUES else value
        return escape(truncate_to_width(rendered, width))
    if isinstance(value, dict):
        return escape(truncate_to_width(summarize_nested(value, item_name="keys"), width))
    if isinstance(value, list):
        return escape(truncate_to_width(summarize_nested(value, item_name="items"), width))
    if value is None:
        return icon_for_status("missing")
    return escape(truncate_to_width(str(value), width))
