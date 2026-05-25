"""Structured shell command helpers."""

from craik.runtime.shell.commands.confirmation import confirmation_result
from craik.runtime.shell.commands.identity import who_result
from craik.runtime.shell.commands.placeholders import compact_stub_result, share_stub_result
from craik.runtime.shell.commands.session_actions import (
    attach_result,
    fork_result,
    note_result,
    redo_result,
)
from craik.runtime.shell.commands.usage import cost_result, quota_result

__all__ = [
    "attach_result",
    "compact_stub_result",
    "confirmation_result",
    "cost_result",
    "fork_result",
    "note_result",
    "quota_result",
    "redo_result",
    "share_stub_result",
    "who_result",
]
