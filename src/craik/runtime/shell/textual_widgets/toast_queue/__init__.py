"""Bounded toast queue for terminal UI notices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from textual.widgets import Static

ToastSeverity = Literal["information", "warning", "error"]

TOAST_TIMEOUTS: dict[ToastSeverity, float | None] = {
    "information": 3,
    "warning": 8,
    "error": None,
}
MAX_VISIBLE_TOASTS = 3


@dataclass(frozen=True)
class ToastNotice:
    """One visible toast notice."""

    message: str
    severity: ToastSeverity = "information"


class ToastQueue(Static):
    """Render the most recent bounded set of notices."""

    def __init__(self, **kwargs: Any) -> None:
        self.notices: list[ToastNotice] = []
        super().__init__("", **kwargs)

    def push(self, message: str, *, severity: ToastSeverity = "information") -> None:
        self.notices.append(ToastNotice(message=message, severity=severity))
        self.notices = self.notices[-MAX_VISIBLE_TOASTS:]
        self.display = True
        self.update(render_toast_queue(self.notices))

    def dismiss(self) -> None:
        if self.notices:
            self.notices.pop()
        self.display = bool(self.notices)
        self.update(render_toast_queue(self.notices))


def render_toast_queue(notices: list[ToastNotice]) -> str:
    """Return a compact multi-line representation of visible notices."""
    return "\n".join(f"{notice.severity}: {notice.message}" for notice in notices)
