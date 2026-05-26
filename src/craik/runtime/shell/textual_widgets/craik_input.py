"""Bordered Craik input widget helpers."""

from __future__ import annotations

import re

from textual.widgets import Input

from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_spec

PASTE_COLLAPSE_THRESHOLD = 3
MULTILINE_HELP_TEXT = (
    "Multi-line: Shift+Enter (native), `\\`+Enter (universal), Ctrl+J "
    "(any terminal), Option/Alt+Enter (macOS Meta)."
)

_CLI_PREFIX_RE = re.compile(
    r"^craik\s+"
    r"(?P<command>auth|model|chat|doctor|migrate|gateway|approvals|session|login|logout|"
    r"whoami|tui|dashboard|desktop|home|insights|usage)\b"
)
_NATURAL_LANGUAGE_SAFE_COMMANDS = {"auth", "exit", "memory", "status"}


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


def slash_command_conversion(text: str) -> str | None:
    """Return a slash-prefixed command when text appears to omit the slash."""
    stripped = text.strip()
    if not stripped or stripped.startswith(("/", "!", "@")):
        return None
    first, separator, rest = stripped.partition(" ")
    normalized = first.lower()
    if get_tui_slash_spec(normalized) is None:
        return None
    if separator and normalized in _NATURAL_LANGUAGE_SAFE_COMMANDS:
        return None
    command = "/" + normalized
    return f"{command}{separator}{rest}" if separator else command


def collapse_paste_placeholder(text: str) -> str | None:
    """Return a single-line placeholder for pasted multi-line content."""
    line_count = text.count("\n") + 1
    if line_count < PASTE_COLLAPSE_THRESHOLD:
        return None
    return f"[{line_count} lines of text]"


def continue_multiline_value(text: str) -> str:
    """Return ``text`` with a trailing continuation marker converted to newline."""
    if text.endswith("\\"):
        return text[:-1] + "\n"
    return text + "\n"


def should_continue_on_submit(text: str) -> bool:
    """Return whether plain Enter should continue instead of submit."""
    return text.endswith("\\")
