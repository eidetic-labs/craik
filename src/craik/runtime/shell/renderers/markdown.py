"""Markdown renderer wrapper."""

from __future__ import annotations

from typing import Any

from rich.markdown import Markdown


def render_markdown(payload: Any) -> Markdown:
    """Render a payload as Rich Markdown."""
    return Markdown(str(payload))
