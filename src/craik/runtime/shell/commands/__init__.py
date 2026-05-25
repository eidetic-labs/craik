"""Structured shell command helpers."""

from craik.runtime.shell.commands.confirmation import confirmation_result
from craik.runtime.shell.commands.identity import who_result
from craik.runtime.shell.commands.placeholders import compact_stub_result, share_stub_result

__all__ = [
    "compact_stub_result",
    "confirmation_result",
    "share_stub_result",
    "who_result",
]
