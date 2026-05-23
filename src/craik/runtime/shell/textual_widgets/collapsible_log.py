"""Collapsible transcript log output helpers."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static

COLLAPSE_THRESHOLD_LINES = 3


class CollapsibleLog(Static):
    """Render long output collapsed until expanded."""

    def __init__(self, text: str, *, expanded: bool = False, **kwargs: Any) -> None:
        self.text = text
        self.expanded = expanded
        super().__init__(collapsible_log_text(text, expanded=expanded), **kwargs)

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.update(collapsible_log_text(self.text, expanded=self.expanded))


def collapsible_log_text(text: str, *, expanded: bool = False) -> str:
    lines = text.splitlines()
    if expanded or len(lines) <= COLLAPSE_THRESHOLD_LINES:
        return text
    hidden = len(lines) - 2
    return "\n".join([*lines[:2], f"… +{hidden} lines"])
