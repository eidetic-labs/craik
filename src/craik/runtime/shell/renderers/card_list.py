"""List-of-cards renderer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from craik.runtime.contract.command_result import NextAction
from craik.runtime.shell.renderers.card import render_card


def render_card_list(
    payload: Sequence[Mapping[str, Any] | Any] | None,
    *,
    title_field: str | None = "name",
    next_actions: Sequence[NextAction] = (),
    empty_state_message: str | None = None,
) -> Group:
    """Render a sequence of entities as vertically stacked cards."""
    if not payload:
        return Group(_empty_card(empty_state_message or "No values."))

    cards: list[Panel] = []
    for index, item in enumerate(payload, start=1):
        if isinstance(item, Mapping):
            title = _title_for(item, title_field=title_field, fallback=f"Item {index}")
            cards.append(
                render_card(
                    item,
                    title=title,
                    next_actions=next_actions,
                )
            )
            continue
        cards.append(render_card({"value": item}, title=f"Item {index}"))
    return Group(*cards)


def _title_for(
    item: Mapping[str, Any],
    *,
    title_field: str | None,
    fallback: str,
) -> str:
    if title_field is None:
        return fallback
    value = item.get(title_field)
    return str(value) if value not in (None, "") else fallback


def _empty_card(message: str) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column()
    table.add_row("empty", message)
    return Panel(table)
