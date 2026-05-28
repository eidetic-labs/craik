"""Callback composition helpers for Claude Code execution hooks."""

from __future__ import annotations

from collections.abc import Callable

from craik.runtime.backend.claude_code_process import ClaudeProcessProtocol


def chain_progress_callbacks(
    first: Callable[[str], None] | None,
    second: Callable[[str], None] | None,
) -> Callable[[str], None] | None:
    if first is None:
        return second
    if second is None:
        return first

    def callback(message: str) -> None:
        first(message)
        second(message)

    return callback


def chain_event_callbacks(
    first: Callable[[dict[str, object]], None] | None,
    second: Callable[[dict[str, object]], None] | None,
) -> Callable[[dict[str, object]], None] | None:
    if first is None:
        return second
    if second is None:
        return first

    def callback(event: dict[str, object]) -> None:
        first(event)
        second(event)

    return callback


def chain_process_callbacks(
    first: Callable[[ClaudeProcessProtocol | None], None] | None,
    second: Callable[[ClaudeProcessProtocol | None], None] | None,
) -> Callable[[ClaudeProcessProtocol | None], None] | None:
    if first is None:
        return second
    if second is None:
        return first

    def callback(process: ClaudeProcessProtocol | None) -> None:
        first(process)
        second(process)

    return callback
