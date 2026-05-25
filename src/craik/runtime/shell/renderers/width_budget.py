"""Terminal-width column budgeting helpers."""

from __future__ import annotations


def budget_columns(
    *,
    num_columns: int,
    terminal_width: int,
    min_width: int = 8,
    gutter: int = 1,
) -> list[int]:
    """Allocate visible column widths within a terminal width budget."""
    if num_columns <= 0 or terminal_width <= 0:
        return []
    available = terminal_width - max(0, num_columns - 1) * gutter
    if available < num_columns * min_width:
        max_cols = max(1, (terminal_width + gutter) // (min_width + gutter))
        return [min_width] * min(max_cols, num_columns)
    equal = max(min_width, available // num_columns)
    return [equal] * num_columns


def truncate_to_width(text: str, width: int) -> str:
    """Truncate text to width, appending an ellipsis if cut."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return f"{text[: width - 1]}…"
