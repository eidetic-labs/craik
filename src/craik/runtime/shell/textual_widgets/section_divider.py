"""Section divider widget for transcript turns."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static


class SectionDivider(Static):
    """Render a subdued horizontal divider between prompt/response turns."""

    def __init__(self, width: int = 72, **kwargs: Any) -> None:
        super().__init__("─" * max(12, width), **kwargs)
