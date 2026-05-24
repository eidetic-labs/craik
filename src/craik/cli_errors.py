"""Process-level CLI error rendering."""

from __future__ import annotations

import os
import sys
from types import TracebackType

import typer


def craik_error_handler(
    exception_type: type[BaseException],
    exception: BaseException,
    traceback: TracebackType | None,
) -> None:
    """Render uncaught CLI failures without leaking locals by default."""
    if os.environ.get("CRAIK_DEBUG") == "1":
        sys.__excepthook__(exception_type, exception, traceback)
        return
    typer.echo(
        f"Internal error: {exception_type.__name__}: {exception}",
        err=True,
    )
    typer.echo("Run with CRAIK_DEBUG=1 for full traceback.", err=True)
    raise SystemExit(2)


def install_craik_error_handler() -> None:
    """Install Craik's non-debug process exception hook."""
    sys.excepthook = craik_error_handler
