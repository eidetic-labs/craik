"""Text-selection hint state for the terminal UI."""

from __future__ import annotations

from craik.runtime.paths import resolve_craik_paths

SELECTION_HINT_MESSAGE = (
    "Text selection: hold Option while dragging on macOS, or Ctrl+Shift in Linux terminals."
)


def first_launch_selection_hint(env: dict[str, str]) -> str | None:
    """Return the text-selection hint once per initialized Craik state directory."""
    if env.get("CRAIK_TUI_SELECTION_HINT") == "0":
        return None
    marker = resolve_craik_paths(env).state / "tui-selection-hint.seen"
    if marker.exists():
        return None
    if marker.parent.exists():
        try:
            marker.write_text("shown\n", encoding="utf-8")
        except OSError:
            return SELECTION_HINT_MESSAGE
    return SELECTION_HINT_MESSAGE
