"""Inline action and approval markers for transcript audit trails."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from textual.widgets import Static

from craik.runtime.shell.textual_widgets.glyph_palette import (
    CHEVRON_TURN,
    RECEIPT_OK,
    RECEIPT_PENDING,
    REVIEW_GLYPH,
    STATE_INFLIGHT,
)

ActionMarkerKind = Literal["tool", "waiting", "approved", "review", "continuation"]

_GLYPHS: dict[ActionMarkerKind, str] = {
    "tool": STATE_INFLIGHT,
    "waiting": RECEIPT_PENDING,
    "approved": RECEIPT_OK,
    "review": REVIEW_GLYPH,
    "continuation": CHEVRON_TURN,
}


@dataclass(frozen=True)
class ActionMarkerData:
    """Structured transcript marker tied to a receipt or state event."""

    kind: ActionMarkerKind
    text: str
    receipt_id: str | None = None


class ActionMarker(Static):
    """Render one inline audit marker."""

    def __init__(self, marker: ActionMarkerData, **kwargs: Any) -> None:
        super().__init__(render_action_marker(marker), **kwargs)
        self.marker = marker


def render_action_marker(marker: ActionMarkerData) -> str:
    suffix = f" ({marker.receipt_id})" if marker.receipt_id else ""
    return f"{_GLYPHS[marker.kind]} {marker.text}{suffix}"
