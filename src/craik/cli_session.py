"""CLI helpers for operator-visible session names."""

from __future__ import annotations

import os

import typer

from craik.runtime.agents.session_naming import SessionNameError, validate_session_name


def env_with_session_name(session_name: str | None) -> dict[str, str]:
    """Return a process env copy with a validated shell session name, if supplied."""
    env = dict(os.environ)
    if session_name is None:
        return env
    try:
        env["CRAIK_SESSION_NAME"] = validate_session_name(session_name)
    except SessionNameError as error:
        raise typer.BadParameter(str(error)) from None
    return env
