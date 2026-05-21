"""Shared runtime text sanitizers for prompt and skill rendering boundaries."""

from __future__ import annotations


def sanitize_runtime_text(value: str, *, limit: int = 2000) -> str:
    """Return a single-line, control-free string safe for runtime rendering."""
    without_controls = "".join(" " if _is_forbidden_control(char) else char for char in value)
    single_line = " ".join(without_controls.replace("\r", "\n").splitlines())
    normalized = " ".join(single_line.split())
    escaped = normalized.replace("`", "\\`")
    while "##" in escaped:
        escaped = escaped.replace("##", "# #")
    return escaped[:limit]


def _is_forbidden_control(char: str) -> bool:
    codepoint = ord(char)
    return codepoint < 32 or codepoint == 127
