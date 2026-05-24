"""Bounded toast queue for terminal UI notices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from rich.markup import escape
from textual.widgets import Static

from craik.runtime.shell.textual_widgets.glyph_palette import WARN_GLYPH

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
        notice = ToastNotice(message=message, severity=severity)
        self.notices.append(notice)
        self.notices = self.notices[-MAX_VISIBLE_TOASTS:]
        self.display = True
        self.update(render_toast_queue(self.notices))
        timeout = TOAST_TIMEOUTS[severity]
        if timeout is not None and self.is_attached:
            self.set_timer(timeout, lambda: self._auto_dismiss(notice))

    def dismiss(self) -> None:
        if self.notices:
            self.notices.pop()
        self.display = bool(self.notices)
        self.update(render_toast_queue(self.notices))

    def _auto_dismiss(self, notice: ToastNotice) -> None:
        if notice not in self.notices:
            return
        self.notices.remove(notice)
        self.display = bool(self.notices)
        self.update(render_toast_queue(self.notices))


def render_toast_queue(notices: list[ToastNotice]) -> str:
    """Return a compact multi-line representation of visible notices."""
    return "\n".join(_render_notice(notice) for notice in notices)


def _render_notice(notice: ToastNotice) -> str:
    prefix = WARN_GLYPH if notice.severity in {"warning", "error"} else "info"
    return f"{escape(prefix)} {escape(notice.severity)}: {escape(notice.message)}"
