"""Structured shell preference command implementations."""

from __future__ import annotations

from craik.runtime.agents.session_naming import SessionNameError, validate_session_name
from craik.runtime.contract import CommandResult
from craik.runtime.shell.session_settings import save_shell_settings
from craik.runtime.shell.textual_widgets.theme_settings import THEMES, current_theme, save_theme


def theme_result(theme: str | None = None, *, env: dict[str, str] | None = None) -> CommandResult:
    """Return or update the current TUI theme."""
    if theme is None:
        return CommandResult(
            payload={"current": current_theme(env), "themes": list(THEMES)},
            shape="kv",
        )
    try:
        settings = save_theme(theme, env)
    except ValueError as error:
        raise ValueError(str(error)) from None
    return CommandResult(payload={"theme": settings.theme}, shape="kv")


def rename_shell_session_result(
    name: str,
    *,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Persist and return the operator-visible shell session name."""
    try:
        display_name = validate_session_name(name)
    except SessionNameError as error:
        raise ValueError(f"invalid session name: {error}") from None
    save_shell_settings(env, session_name=display_name)
    if env is not None:
        env["CRAIK_SESSION_NAME"] = display_name
    return CommandResult(payload={"session_name": display_name}, shape="kv")
