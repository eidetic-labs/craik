"""Transient accent glyph for terminal UI state changes."""

from __future__ import annotations

from textual.widgets import Static

from craik.runtime.shell.textual_widgets.brand_tokens import CRAIK_BRAND_LAVENDER
from craik.runtime.shell.textual_widgets.glyph_palette import RECEIPT_OK, STATE_INFLIGHT


class AccentEmission(Static):
    """Flash a short lavender state marker above the bottom hint bar."""

    DEFAULT_CSS = f"""
    AccentEmission {{
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: {CRAIK_BRAND_LAVENDER};
    }}
    """

    current_glyph: str = ""

    def flash(self, kind: str = "state") -> None:
        """Render a transient accent glyph for a state or receipt event."""
        glyph = RECEIPT_OK if kind == "receipt" else STATE_INFLIGHT
        self.current_glyph = glyph
        self.update(glyph)
        self.set_timer(0.6, self.clear)

    def clear(self) -> None:
        """Clear the transient accent marker."""
        self.current_glyph = ""
        self.update("")
