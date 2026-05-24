"""Blank footer safe area for the terminal UI bottom hint bar."""

from __future__ import annotations

from textual.widgets import Static


class FooterSafeArea(Static):
    """Reserve one quiet row below the status bar."""

    DEFAULT_CSS = """
    FooterSafeArea {
        dock: bottom;
        height: 1;
    }
    """
