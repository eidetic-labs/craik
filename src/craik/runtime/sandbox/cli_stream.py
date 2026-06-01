"""Generic CLI subprocess streaming for audited vendor-CLI runs (Task 5.5b).

Generalizes the Claude Code subprocess-management structure
(``backend.claude_code._execute_claude_code_prompt``) into a vendor-neutral
stream pump usable by ANY ``argv``-launched CLI (e.g. ``gemini`` /  ``codex``):
spawn the process via the reviewed local-process boundary (argv list only,
never ``shell=True``), stream stdout lines off a daemon reader thread, hand each
non-empty line to an ``on_line`` sink as it arrives, and end with a BOUNDED wait
so the pump never hangs. Process failure (nonzero exit), no output, timeout, and
operator interrupt are each handled gracefully and reported on the returned
:class:`CliStreamOutcome` -- callers map those to a completed-with-error run
rather than crashing.

This is the subprocess seam ONLY: it persists nothing and emits no events. The
audited orchestration (store/task/run/receipt persistence) lives in
``backend.adapters.audited_core.run_cli_core``, which drives this pump. It lives
in ``sandbox`` (next to ``local_process_backend``) because it is reviewed
local-process execution, and because both ``backend`` and ``backend/adapters``
are at the sibling-module layout cap.
"""

from __future__ import annotations

import queue
import subprocess  # nosec B404 - types only; argv-only spawn via start_reviewed_local_process.
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import IO

from craik.runtime.sandbox.local_process_backend import (
    LocalProcessStartError,
    LocalProcessTimeoutExpired,
    start_reviewed_local_process,
)

# Bounded wait after the stream ends so a wedged child never hangs the pump.
_EXIT_WAIT_SECONDS = 30.0
# Heartbeat / cancel poll cadence while draining stdout.
_POLL_SECONDS = 1.0


class CliStreamInterrupted(RuntimeError):
    """Raised internally when the operator cancels a streaming CLI run."""


@dataclass
class CliStreamOutcome:
    """Result of pumping a vendor CLI subprocess.

    ``status`` is ``"completed"`` on a clean zero exit with output, ``"failed"``
    on a nonzero exit / start error / empty output, and ``"interrupted"`` when a
    cancel event fired. ``error`` carries a short diagnostic for the failure /
    interrupt paths (``None`` on success); ``lines`` is every non-empty stdout
    line in arrival order.
    """

    status: str
    returncode: int | None
    lines: list[str] = field(default_factory=list)
    error: str | None = None


def stream_cli_subprocess(
    argv: list[str],
    env: Mapping[str, str],
    *,
    on_line: Callable[[str], None],
    cancel_event: threading.Event | None = None,
    timeout_seconds: float = _EXIT_WAIT_SECONDS,
) -> CliStreamOutcome:
    """Spawn ``argv`` with ``env``, stream stdout lines to ``on_line``, return outcome.

    Never raises for an ordinary subprocess failure: a start error, nonzero
    exit, post-stream timeout, empty output, or operator interrupt all return a
    :class:`CliStreamOutcome` with the appropriate non-completed ``status`` and a
    diagnostic ``error``. ``on_line`` receives each stripped non-empty stdout
    line as it arrives (the caller parses + feeds the typed mapper). The child is
    terminated on interrupt and killed if it will not exit within the bounded
    wait, so the pump cannot hang.
    """
    try:
        process = start_reviewed_local_process(
            list(argv),
            stdout="pipe",
            stderr="stdout",
            env=dict(env),
        )
    except (OSError, LocalProcessStartError) as exc:
        return CliStreamOutcome(status="failed", returncode=None, error=str(exc))

    lines: list[str] = []
    interrupted = False
    if process.stdout is not None:
        line_queue: queue.Queue[str | None] = queue.Queue()
        reader = threading.Thread(
            target=_drain_stdout,
            args=(process.stdout, line_queue),
            name="craik-cli-stream-stdout",
            daemon=True,
        )
        reader.start()
        while True:
            if cancel_event is not None and cancel_event.is_set():
                interrupted = True
                _terminate(process)
                break
            try:
                raw_line = line_queue.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                if process.poll() is not None and line_queue.empty():
                    break
                continue
            if raw_line is None:
                break
            stripped = raw_line.strip()
            if not stripped:
                continue
            lines.append(stripped)
            on_line(stripped)

    if interrupted:
        return CliStreamOutcome(
            status="interrupted",
            returncode=process.poll(),
            lines=lines,
            error="Audited run interrupted by operator.",
        )
    return _finalize(process, lines, timeout_seconds)


def _finalize(
    process: subprocess.Popen[str], lines: list[str], timeout_seconds: float
) -> CliStreamOutcome:
    try:
        return_code = process.wait(timeout=timeout_seconds)
    except LocalProcessTimeoutExpired:
        process.kill()
        return CliStreamOutcome(
            status="failed",
            returncode=None,
            lines=lines,
            error="CLI did not exit after the stream ended.",
        )
    if return_code != 0:
        return CliStreamOutcome(
            status="failed",
            returncode=return_code,
            lines=lines,
            error=f"CLI exited with code {return_code}.",
        )
    if not lines:
        return CliStreamOutcome(
            status="failed",
            returncode=return_code,
            lines=lines,
            error="CLI produced no output.",
        )
    return CliStreamOutcome(status="completed", returncode=return_code, lines=lines)


def _drain_stdout(stream: IO[str], line_queue: queue.Queue[str | None]) -> None:
    try:
        for raw_line in stream:
            line_queue.put(str(raw_line))
    finally:
        line_queue.put(None)


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.05)
    process.kill()


__all__ = ["CliStreamInterrupted", "CliStreamOutcome", "stream_cli_subprocess"]
