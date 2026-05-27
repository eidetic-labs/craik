"""Claude Code process helper functions."""

from __future__ import annotations

import queue
from collections.abc import Iterator
from typing import IO, Protocol, cast


class ClaudeProcessProtocol(Protocol):
    stdout: IO[str] | None
    returncode: int | None
    pid: int

    def poll(self) -> int | None:
        raise NotImplementedError

    def wait(self, timeout: float | None = None) -> int:
        raise NotImplementedError

    def terminate(self) -> None:
        raise NotImplementedError

    def kill(self) -> None:
        raise NotImplementedError


def _terminate_claude_code_process(process: ClaudeProcessProtocol) -> None:
    if process.poll() is not None:
        return
    process.terminate()


def _read_claude_code_stdout(
    stream: object,
    line_queue: queue.Queue[str | None],
) -> None:
    try:
        for raw_line in cast(Iterator[object], stream):
            line_queue.put(str(raw_line))
    finally:
        line_queue.put(None)
