"""Section divider widget for transcript turns."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static

from craik.runtime.shell.textual_widgets.glyph_palette import DOT_LEADER


class SectionDivider(Static):
    """Render a subdued horizontal divider between prompt/response turns."""

    current_divider: str

    def __init__(self, width: int = 72, **kwargs: Any) -> None:
        self.current_divider = DOT_LEADER.center(max(12, width))
        super().__init__(self.current_divider, **kwargs)
