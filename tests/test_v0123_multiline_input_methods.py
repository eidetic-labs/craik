from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.craik_input import (
    MULTILINE_HELP_TEXT,
    CraikInput,
    continue_multiline_value,
    should_continue_on_submit,
)


def test_backslash_enter_converts_marker_to_newline() -> None:
    assert should_continue_on_submit("line one\\") is True
    assert continue_multiline_value("line one\\") == "line one\n"


def test_ctrl_j_and_alt_enter_newline_helpers_are_equivalent() -> None:
    assert continue_multiline_value("line one") == "line one\n"
    assert continue_multiline_value("line one\nline two") == "line one\nline two\n"


def test_plain_enter_without_backslash_submits() -> None:
    assert should_continue_on_submit("line one") is False


def test_help_discovers_multiline_input_methods() -> None:
    result = dispatch_slash_command("/help")

    assert MULTILINE_HELP_TEXT in result.text
    assert "Ctrl+J" in result.text
    assert "Option/Alt+Enter" in result.text


@pytest.mark.parametrize("key", ["ctrl+j", "alt+enter"])
def test_bound_newline_key_inserts_newline_via_pilot(tmp_path: Path, key: str) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            input_widget = pilot.app.query_one("#input", CraikInput)
            input_widget.focus()
            await pilot.press("h", "i")
            await pilot.press(key)
            await pilot.pause()
            await pilot.press("t", "h", "e", "r", "e")
            assert input_widget.value == "hi\nthere"

    asyncio.run(run())


def test_backslash_continuation_extends_buffer_via_pilot(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            input_widget = pilot.app.query_one("#input", CraikInput)
            input_widget.focus()
            await pilot.press("h", "i", "\\", "enter")
            assert input_widget.value == "hi\n"
            await pilot.press("t", "h", "e", "r", "e")
            assert input_widget.value == "hi\nthere"

    asyncio.run(run())


def test_shift_enter_inserts_newline_via_pilot(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            input_widget = pilot.app.query_one("#input", CraikInput)
            input_widget.focus()
            await pilot.press("h", "i")
            await pilot.press("shift+enter")
            await pilot.pause()
            await pilot.press("t", "h", "e", "r", "e")
            assert input_widget.value == "hi\nthere"

    asyncio.run(run())


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}
