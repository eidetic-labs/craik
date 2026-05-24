"""Persistent shell session settings."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from craik.runtime.paths import resolve_craik_paths


def active_session_id(env: dict[str, str] | None) -> str | None:
    """Return the active persistent session id selected by the shell."""
    payload = load_shell_settings(env)
    value = payload.get("active_session")
    return value if isinstance(value, str) and value.strip() else None


def shell_session_name(env: dict[str, str] | None) -> str | None:
    """Return the current operator-visible shell session name."""
    values = os.environ if env is None else env
    env_name = values.get("CRAIK_SESSION_NAME")
    if env_name:
        return env_name
    payload = load_shell_settings(env)
    value = payload.get("session_name")
    return value if isinstance(value, str) and value.strip() else None


def save_active_session(session_id: str, env: dict[str, str] | None) -> None:
    """Persist the active session id without discarding other shell settings."""
    save_shell_settings(env, active_session=session_id)


def save_shell_settings(
    env: dict[str, str] | None,
    *,
    active_session: str | None = None,
    session_name: str | None = None,
) -> None:
    """Persist selected shell settings atomically."""
    path = _shell_settings_path(env)
    payload = load_shell_settings(env)
    if active_session is not None:
        payload["active_session"] = active_session
    if session_name is not None:
        payload["session_name"] = session_name
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".shell-settings.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def load_shell_settings(env: dict[str, str] | None) -> dict[str, Any]:
    """Load persisted shell settings, returning an empty mapping on invalid files."""
    path = _shell_settings_path(env)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _shell_settings_path(env: dict[str, str] | None) -> Path:
    return resolve_craik_paths(env).config / "shell-settings.json"
