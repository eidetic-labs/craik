"""Current-session transcript search overlay."""

from __future__ import annotations

from dataclasses import dataclass

from rich.markup import escape
from textual.widgets import Static

from craik.runtime.shell.textual_widgets.glyph_palette import BULLET_SEPARATOR


@dataclass(frozen=True)
class TranscriptSearchState:
    """Search state for the active transcript."""

    query: str
    matches: tuple[str, ...]
    index: int = 0


class TranscriptSearchOverlay(Static):
    """Search the current in-memory transcript."""

    can_focus = True

    def __init__(
        self,
        *,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        self.lines: list[str] = []
        self.state = TranscriptSearchState("", ())
        super().__init__("", id=id, classes=classes, disabled=disabled)

    def open(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.state = TranscriptSearchState("", ())
        self.display = True
        self._refresh_content()

    def dismiss(self) -> None:
        self.display = False

    def append_query(self, character: str) -> None:
        self._set_query(self.state.query + character)

    def backspace(self) -> None:
        self._set_query(self.state.query[:-1])

    def move(self, offset: int) -> None:
        if not self.state.matches:
            return
        self.state = TranscriptSearchState(
            self.state.query,
            self.state.matches,
            (self.state.index + offset) % len(self.state.matches),
        )
        self._refresh_content()

    def _set_query(self, query: str) -> None:
        normalized = query.lower()
        matches = tuple(line for line in self.lines if normalized and normalized in line.lower())
        self.state = TranscriptSearchState(query, matches)
        self._refresh_content()

    def _refresh_content(self) -> None:
        if not self.state.query:
            self.update("Find in transcript: ")
            return
        if not self.state.matches:
            self.update(f"Find: {escape(self.state.query)} {BULLET_SEPARATOR} no matches")
            return
        current = self.state.matches[self.state.index]
        self.update(
            f"Find: {escape(self.state.query)} {BULLET_SEPARATOR} "
            f"{self.state.index + 1}/{len(self.state.matches)} {BULLET_SEPARATOR} "
            f"{escape(current)}"
        )
