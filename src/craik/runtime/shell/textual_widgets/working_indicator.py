"""Live working indicator for in-flight terminal UI actions."""

from __future__ import annotations

from textual.widgets import Static

from craik.runtime.shell.textual_widgets.glyph_palette import BULLET_SEPARATOR, STATE_INFLIGHT


class WorkingIndicator(Static):
    """Show elapsed work state above the input region."""

    DEFAULT_CSS = """
    WorkingIndicator {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $accent;
    }
    """

    def set_elapsed(self, seconds: int) -> None:
        minutes, remainder = divmod(max(0, seconds), 60)
        elapsed = f"{minutes}m {remainder}s" if minutes else f"{remainder}s"
        self.update(f"{STATE_INFLIGHT} Working ({elapsed} {BULLET_SEPARATOR} esc to interrupt)")
