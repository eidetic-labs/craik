"""Transient accent glyph for terminal UI state changes."""

from __future__ import annotations

from textual.widgets import Static

from craik.runtime.shell.textual_widgets.brand_tokens import CRAIK_BRAND_LAVENDER, CRAIK_GREY_400
from craik.runtime.shell.textual_widgets.glyph_palette import RECEIPT_OK, STATE_INFLIGHT

ACCENT_HOLD_SECONDS = 0.6
ACCENT_FADE_SECONDS = 0.8


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
        """Render a transient accent glyph and fade it to neutral."""
        glyph = RECEIPT_OK if kind == "receipt" else STATE_INFLIGHT
        self.current_glyph = glyph
        self.styles.color = CRAIK_BRAND_LAVENDER
        self.update(glyph)
        self.styles.animate(
            "color",
            value=CRAIK_GREY_400,
            duration=ACCENT_FADE_SECONDS,
            delay=ACCENT_HOLD_SECONDS,
            on_complete=self.clear,
        )

    def clear(self) -> None:
        """Clear the transient accent marker."""
        self.current_glyph = ""
        self.update("")
