from __future__ import annotations

import json
from pathlib import Path

from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_app import resolve_textual_theme
from craik.runtime.shell.textual_widgets.theme_settings import current_theme


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def test_theme_slash_command_lists_current_theme(tmp_path: Path) -> None:
    result = dispatch_slash_command("/theme", env=_env(tmp_path))

    payload = json.loads(result.text)
    assert payload["current"] == "dark"
    assert payload["themes"] == ["dark", "light", "monochrome"]


def test_theme_slash_command_persists_theme_and_updates_env(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = dispatch_slash_command("/theme light", env=env)

    assert result.exit_code == 0
    assert result.text == "Theme set to `light`."
    assert env["CRAIK_THEME"] == "light"
    assert current_theme(env) == "light"
    assert resolve_textual_theme(env) == "light"


def test_theme_slash_command_rejects_unknown_theme(tmp_path: Path) -> None:
    result = dispatch_slash_command("/theme neon", env=_env(tmp_path))

    assert result.exit_code == 2
    assert "unknown theme" in result.text


def test_textual_theme_resolver_reads_persisted_theme(tmp_path: Path) -> None:
    env = _env(tmp_path)
    dispatch_slash_command("/theme monochrome", env=env)
    env.pop("CRAIK_THEME")

    assert resolve_textual_theme(env) == "monochrome"
