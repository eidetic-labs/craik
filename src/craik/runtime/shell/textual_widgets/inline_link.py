"""Inline link detection helpers for transcript content."""

from __future__ import annotations

import re

URL_RE = re.compile(r"https?://[^\s)>\"]+")


def linkify_text(text: str) -> str:
    """Return Textual/Rich markup for URLs in transcript text."""

    def _replace(match: re.Match[str]) -> str:
        url = match.group(0)
        return f"[@click=open_url('{url}')][u]{url}[/u][/@click]"

    return URL_RE.sub(_replace, text)
