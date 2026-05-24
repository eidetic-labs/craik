"""Structured renderers for slash command payloads."""

from __future__ import annotations

import json
from typing import Any

from rich.markdown import Markdown
from rich.table import Table
from rich.tree import Tree
from textual.widgets import RichLog

from craik.runtime.shell.slash_command_schema import PayloadShape
from craik.runtime.shell.slash_commands import SlashCommandResult
from craik.runtime.shell.textual_widgets.brand_tokens import (
    CRAIK_BRAND_LAVENDER,
    CRAIK_GREY_400,
)
from craik.runtime.shell.textual_widgets.inline_link import linkify_text

COLLAPSE_RENDER_LINE_THRESHOLD = 50


def write_slash_command_result(transcript: RichLog, result: SlashCommandResult) -> None:
    """Write a slash command result using structured rendering when available."""
    if result.empty_state_message is not None:
        transcript.write(_empty_state_payload(result))
        return
    if result.payload is None or result.payload_shape is None:
        transcript.write(linkify_text(result.text))
        return
    transcript.write(render_slash_payload(result.payload, shape=result.payload_shape))


def render_slash_payload(payload: Any, *, shape: PayloadShape) -> object:
    """Return a Rich renderable for a slash command payload."""
    if shape == "table":
        return _table_payload(payload)
    if shape == "kv":
        return _kv_payload(payload)
    if shape == "tree":
        return _tree_payload(payload)
    if shape == "markdown":
        return Markdown(str(payload))
    return str(payload)


def _table_payload(payload: Any) -> Table:
    rows = _table_rows(payload)
    hidden = max(0, len(rows) - COLLAPSE_RENDER_LINE_THRESHOLD)
    if hidden:
        rows = rows[:COLLAPSE_RENDER_LINE_THRESHOLD]
    table = Table(show_header=True, header_style=CRAIK_BRAND_LAVENDER, expand=True)
    if not rows:
        table.add_column("result")
        table.add_row("No rows")
        return table
    columns = _stable_columns(rows)
    for column in columns:
        table.add_column(column.replace("_", " "), style=CRAIK_GREY_400)
    for row in rows:
        table.add_row(*[_cell(row.get(column)) for column in columns])
    if hidden:
        table.add_row(
            *[
                f"… +{hidden} lines (Space=expand, Ctrl+F=find)" if index == 0 else ""
                for index, _column in enumerate(columns)
            ]
        )
    return table


def _empty_state_payload(result: SlashCommandResult) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style=CRAIK_BRAND_LAVENDER, no_wrap=True)
    table.add_column(style=CRAIK_GREY_400)
    table.add_row("empty", result.empty_state_message or "")
    if result.empty_state_remediation:
        table.add_row("next", result.empty_state_remediation)
    return table


def _kv_payload(payload: Any) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style=CRAIK_BRAND_LAVENDER, no_wrap=True)
    table.add_column(style=CRAIK_GREY_400)
    if isinstance(payload, dict):
        items = list(payload.items())
    else:
        items = [("value", payload)]
    for key, value in items:
        table.add_row(str(key).replace("_", " "), _cell(value))
    return table


def _tree_payload(payload: Any) -> Tree:
    tree = Tree("result")
    _add_tree_value(tree, payload)
    return tree


def _add_tree_value(node: Tree, value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            branch = node.add(str(key).replace("_", " "))
            _add_tree_value(branch, child)
        return
    if isinstance(value, list):
        for index, child in enumerate(value, start=1):
            branch = node.add(f"[{index}]")
            _add_tree_value(branch, child)
        return
    node.add(_cell(value))


def _table_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            row if isinstance(row, dict) else {"value": row}
            for row in payload
        ]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return [
                    row if isinstance(row, dict) else {"value": row}
                    for row in value
                ]
        return [{"key": key, "value": value} for key, value in payload.items()]
    return [{"value": payload}]


def _stable_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    return json.dumps(value, sort_keys=True, default=str)
