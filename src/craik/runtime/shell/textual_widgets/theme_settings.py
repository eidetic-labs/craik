"""Persistent TUI theme settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

from craik.runtime.paths import resolve_craik_paths

ThemeName = Literal["dark", "light", "monochrome"]
THEMES: tuple[ThemeName, ...] = ("dark", "light", "monochrome")


@dataclass(frozen=True)
class ThemeSettings:
    """Persisted terminal UI theme setting."""

    theme: ThemeName


def current_theme(env: dict[str, str] | None = None) -> ThemeName:
    """Return the configured theme without terminal auto-detection."""
    configured = configured_theme(env)
    return configured or "dark"


def configured_theme(env: dict[str, str] | None = None) -> ThemeName | None:
    """Return an explicit theme from env or disk, if one has been configured."""
    values = dict(os.environ) if env is None else env
    override = values.get("CRAIK_THEME", "").strip().lower()
    if override in THEMES:
        return override  # type: ignore[return-value]
    path = resolve_craik_paths(values).config / "theme.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    theme = str(payload.get("theme", "")).strip().lower()
    return theme if theme in THEMES else None  # type: ignore[return-value]


def save_theme(theme: str, env: dict[str, str] | None = None) -> ThemeSettings:
    """Persist a valid TUI theme and update the provided environment mapping."""
    normalized = theme.strip().lower()
    if normalized not in THEMES:
        raise ValueError("unknown theme: choose dark, light, or monochrome")
    values = dict(os.environ) if env is None else env
    path = resolve_craik_paths(values).config / "theme.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"theme": normalized}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if env is not None:
        env["CRAIK_THEME"] = normalized
    return ThemeSettings(theme=normalized)  # type: ignore[arg-type]
