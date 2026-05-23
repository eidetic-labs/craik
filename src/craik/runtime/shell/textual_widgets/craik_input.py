"""Bordered Craik input widget helpers."""

from __future__ import annotations

import re

from textual.widgets import Input

PASTE_COLLAPSE_THRESHOLD = 3

_CLI_PREFIX_RE = re.compile(
    r"^craik\s+"
    r"(?P<command>auth|model|chat|doctor|migrate|gateway|approvals|session|login|logout|"
    r"whoami|tui|dashboard|desktop|home|insights|usage)\b"
)


class CraikInput(Input):
    """Input widget that blocks shell-command-shaped chat submissions."""

    DEFAULT_CSS = """
    CraikInput {
        dock: bottom;
        border: round $primary;
        padding: 0 1;
        height: 3;
    }
    """

    def cli_prefix_match(self) -> str | None:
        match = _CLI_PREFIX_RE.match(self.value.strip())
        return match.group("command") if match else None


def cli_prefix_warning(text: str) -> str | None:
    """Return the operator warning for a shell-command-shaped prompt."""
    match = _CLI_PREFIX_RE.match(text.strip())
    if match is None:
        return None
    command = match.group("command")
    return (
        f"`craik {command}` looks like a CLI command. Try `/{command}` for the in-TUI "
        "version, or press Ctrl-D to exit and run from your operator shell."
    )


def collapse_paste_placeholder(text: str) -> str | None:
    """Return a single-line placeholder for pasted multi-line content."""
    line_count = text.count("\n") + 1
    if line_count < PASTE_COLLAPSE_THRESHOLD:
        return None
    return f"[{line_count} lines of text]"
