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

    def set_elapsed(
        self,
        seconds: int,
        *,
        backend: str | None = None,
        queued: int = 0,
    ) -> None:
        minutes, remainder = divmod(max(0, seconds), 60)
        elapsed = f"{minutes}m {remainder}s" if minutes else f"{remainder}s"
        pulse = "." * ((seconds % 3) + 1)
        label = backend or "Model"
        queue_text = f" {BULLET_SEPARATOR} queued {queued}" if queued else ""
        self.update(f"{STATE_INFLIGHT} {label} thinking{pulse} ({elapsed}{queue_text})")
