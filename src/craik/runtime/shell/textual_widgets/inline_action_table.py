"""Focusable inline table with canonical action-key mapping."""

from __future__ import annotations

from typing import Any

from textual.message import Message
from textual.widgets import DataTable

from craik.runtime.shell.slash_command_schema import ActionKeySet


class InlineActionTable(DataTable[str]):
    """DataTable that exposes the action registered for a pressed key."""

    class InlineActionRequested(Message):
        """Posted when an operator invokes a canonical row action."""

        def __init__(self, command_name: str, action: str, row_id: str) -> None:
            super().__init__()
            self.command_name = command_name
            self.action = action
            self.row_id = row_id

    BINDINGS = [
        ("enter", "select_cursor", "Open"),
        ("d", "dispatch_action_key('D')", "Delete"),
        ("r", "dispatch_action_key('R')", "Rename"),
        ("a", "dispatch_action_key('A')", "Approve"),
        ("/", "dispatch_action_key('/')", "Search"),
        ("f", "dispatch_action_key('F')", "Filter"),
        ("escape", "dispatch_action_key('escape')", "Cancel"),
    ]

    def __init__(
        self,
        *,
        action_keys: ActionKeySet,
        rows: list[dict[str, Any]],
        command_name: str = "",
        row_id_field: str = "id",
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.action_keys = action_keys
        self.action_log: list[str] = []
        self._rows = rows
        self._command_name = command_name
        self._row_id_field = row_id_field

    def on_mount(self) -> None:
        self.cursor_type = "row"
        columns = _stable_columns(self._rows)
        for column in columns:
            self.add_column(column.replace("_", " "), key=column)
        for row in self._rows:
            self.add_row(*[str(row.get(column, "")) for column in columns])

    def action_select_cursor(self) -> None:
        self._dispatch_action("enter")

    def action_dispatch_action_key(self, key: str) -> None:
        self._dispatch_action(key)

    def action_for_key(self, key: str) -> str | None:
        """Return the configured action for a canonical key."""
        values = self.action_keys.model_dump(exclude_none=True, by_alias=True)
        return values.get(key)

    def _dispatch_action(self, key: str) -> None:
        action = self.action_for_key(key)
        if action is None:
            return
        self.action_log.append(action)
        row_id = self._current_row_id()
        if not self._command_name or not row_id:
            return
        self.post_message(self.InlineActionRequested(self._command_name, action, row_id))

    def _current_row_id(self) -> str | None:
        row_index = self.cursor_row
        if row_index is None or row_index >= len(self._rows):
            return None
        value = self._rows[row_index].get(self._row_id_field)
        if value in (None, ""):
            return None
        return str(value)


def _stable_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns or ["result"]
