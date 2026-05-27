"""Claude Code process helper functions."""

from __future__ import annotations

import queue
from collections.abc import Iterator
from typing import Protocol, cast


class _TerminableProcess(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


def _terminate_claude_code_process(process: _TerminableProcess) -> None:
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

