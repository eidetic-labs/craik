"""Shared CLI operator-session helpers."""

from __future__ import annotations

from typing import NoReturn

import typer

from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore


def operator_identity_or_fail() -> str:
    """Return the active operator subject or exit with the canonical CLI error."""
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        _fail("active operator session required; run craik login")
    return session.subject


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(2)
