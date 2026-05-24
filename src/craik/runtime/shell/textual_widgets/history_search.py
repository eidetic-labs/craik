"""Reverse-history search overlay for the canonical terminal UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.markup import escape
from textual.widgets import Static

from craik.runtime.shell.shell_history import search_history

HistoryScope = Literal["session", "project", "all"]


@dataclass(frozen=True)
class HistorySelection:
    """Selected reverse-history search result."""

    text: str
    submit: bool = False


class HistorySearchOverlay(Static):
    """Small stateful overlay for reverse history search."""

    DEFAULT_CSS = """
    HistorySearchOverlay {
        dock: bottom;
        margin: 0 2 4 2;
        border: round $primary;
        height: auto;
        max-height: 8;
        padding: 0 1;
    }
    """

    scope: HistoryScope = "session"

    def __init__(self, *, env: dict[str, str] | None = None, id: str | None = None) -> None:
        super().__init__("", id=id)
        self.env = env
        self.search_query = ""
        self.matches: list[str] = []
        self.selected_index = 0

    def open(self, *, initial_query: str = "") -> None:
        """Open the overlay and refresh matches."""
        self.search_query = initial_query
        self.selected_index = 0
        self.display = True
        self.refresh_matches()

    def dismiss(self) -> None:
        """Hide the overlay without changing the input buffer."""
        self.display = False

    def cycle_scope(self) -> HistoryScope:
        """Cycle the visible search scope label."""
        scopes: tuple[HistoryScope, ...] = ("session", "project", "all")
        self.scope = scopes[(scopes.index(self.scope) + 1) % len(scopes)]
        self.refresh_matches()
        return self.scope

    def append_query(self, text: str) -> None:
        """Append typed search text and refresh live matches."""
        self.search_query += text
        self.selected_index = 0
        self.refresh_matches()

    def backspace(self) -> None:
        """Remove one search character and refresh live matches."""
        self.search_query = self.search_query[:-1]
        self.selected_index = 0
        self.refresh_matches()

    def move(self, delta: int) -> None:
        """Move the selected match up or down."""
        if not self.matches:
            return
        self.selected_index = (self.selected_index + delta) % len(self.matches)
        self.refresh_display()

    def selected(self, *, submit: bool = False) -> HistorySelection | None:
        """Return the selected match, optionally marked for immediate submit."""
        if not self.matches:
            return None
        return HistorySelection(self.matches[self.selected_index], submit=submit)

    def refresh_matches(self) -> None:
        """Refresh matches from persisted shell history."""
        self.matches = search_history(self.search_query, env=self.env)
        if self.selected_index >= len(self.matches):
            self.selected_index = 0
        self.refresh_display()

    def refresh_display(self) -> None:
        """Render current query, scope, and up to five matches."""
        if not self.matches:
            self.update(
                f"[b]reverse-i-search[/b] ({self.scope}) `{escape(self.search_query)}`\n"
                "No history"
            )
            return
        rows = [f"[b]reverse-i-search[/b] ({self.scope}) `{escape(self.search_query)}`"]
        for index, value in enumerate(self.matches[:5]):
            marker = ">" if index == self.selected_index else " "
            rows.append(f"{marker} {escape(value)}")
        self.update("\n".join(rows))
