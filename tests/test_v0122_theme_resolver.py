from __future__ import annotations

import json

from craik.runtime.shell.textual_app import resolve_textual_theme, terminal_supports_textual


def test_theme_resolver_honors_explicit_override() -> None:
    assert resolve_textual_theme({"CRAIK_THEME": "light"}) == "light"
    assert resolve_textual_theme({"CRAIK_THEME": "monochrome"}) == "monochrome"


def test_theme_resolver_honors_no_color() -> None:
    assert resolve_textual_theme({"NO_COLOR": "1"}) == "monochrome"


def test_theme_resolver_uses_colorfgbg_background_hint() -> None:
    assert resolve_textual_theme({"COLORFGBG": "15;0"}) == "dark"
    assert resolve_textual_theme({"COLORFGBG": "0;15"}) == "light"


def test_theme_resolver_partial_env_ignores_persisted_user_theme(tmp_path) -> None:
    home = tmp_path / ".craik"
    config = home / "config"
    config.mkdir(parents=True)
    (config / "theme.json").write_text(json.dumps({"theme": "monochrome"}), encoding="utf-8")

    assert resolve_textual_theme({"COLORFGBG": "15;0"}) == "dark"
    assert resolve_textual_theme({"CRAIK_HOME": str(home), "COLORFGBG": "15;0"}) == (
        "monochrome"
    )


def test_terminal_supports_textual_respects_degraded_modes() -> None:
    assert terminal_supports_textual({"TERM": "xterm-256color"})
    assert not terminal_supports_textual({"CRAIK_NO_TUI": "1", "TERM": "xterm-256color"})
    assert not terminal_supports_textual({"TERM": "dumb"})
