from __future__ import annotations

import asyncio
from pathlib import Path

from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.craik_input import (
    cli_prefix_warning,
    collapse_paste_placeholder,
)
from craik.runtime.shell.textual_widgets.status_bar import StatusBar


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def test_textual_app_mounts_status_bar_and_welcome(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            assert "Craik" in pilot.app.query_one("#status", StatusBar).current_status

    asyncio.run(run())


def test_textual_app_shows_slash_popup(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            await pilot.press("/")
            assert pilot.app.query_one("#slash-popup").display

    asyncio.run(run())


def test_cli_prefix_warning_preserves_command_intent() -> None:
    warning = cli_prefix_warning("craik auth login openai")

    assert warning is not None
    assert "`/auth`" in warning
    assert "Ctrl-D" in warning


def test_paste_collapse_threshold() -> None:
    assert collapse_paste_placeholder("one\ntwo") is None
    assert collapse_paste_placeholder("one\ntwo\nthree") == "[3 lines of text]"
