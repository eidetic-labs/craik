"""Collapse nested values into compact summary scalars."""

from __future__ import annotations

from typing import Any


def summarize_nested(value: Any, *, item_name: str = "items", show_first: int = 3) -> str:
    """Render a nested dict/list as a count plus a short sample."""
    if isinstance(value, dict):
        count = len(value)
        first_names = list(value.keys())[:show_first]
        sample = _sample(first_names, count=count, show_first=show_first)
        return f"{count} {item_name} ({sample})" if sample else f"{count} {item_name}"
    if isinstance(value, list):
        count = len(value)
        first_items = value[:show_first]
        sample = _sample(first_items, count=count, show_first=show_first)
        return f"{count} {item_name} ({sample})" if sample else f"{count} {item_name}"
    return str(value)


def _sample(values: list[Any], *, count: int, show_first: int) -> str:
    sample = ", ".join(_sample_value(value) for value in values)
    if count > show_first:
        return f"{sample}, ..." if sample else "..."
    return sample


def _sample_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "id", "provider", "mode"):
            raw = value.get(key)
            if raw is not None:
                return str(raw)
        return f"{len(value)} keys"
    return str(value)
