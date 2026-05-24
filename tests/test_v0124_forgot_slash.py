from __future__ import annotations

import asyncio
from pathlib import Path

from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.craik_input import (
    CraikInput,
    slash_command_conversion,
)


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def test_forgot_slash_conversion_recognizes_registered_commands() -> None:
    assert slash_command_conversion("provider") == "/provider"
    assert slash_command_conversion("Provider login openai") == "/provider login openai"
    assert slash_command_conversion("/provider") is None
    assert slash_command_conversion("! provider") is None
    assert slash_command_conversion("@provider") is None
    assert slash_command_conversion("ordinary prompt") is None


def test_forgot_slash_tab_converts_and_dispatches(tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "provider"
            await pilot.press("enter")
            assert input_widget.value == "provider"
            await pilot.press("tab")
            assert input_widget.value == ""

    asyncio.run(run())


def test_forgot_slash_enter_override_sends_prompt(tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "provider availability today"
            await pilot.press("enter")
            assert input_widget.value == "provider availability today"
            await pilot.press("enter")
            assert input_widget.value == ""

    asyncio.run(run())


def test_missing_required_argument_renders_command_help() -> None:
    result = dispatch_slash_command("/rename")

    assert result.command_name == "help"
    assert result.payload_shape == "markdown"
    assert "Usage: `/rename <name>`" in result.text
    assert "`name`" in result.text


def test_model_set_without_selector_renders_argument_help() -> None:
    result = dispatch_slash_command("/model set")

    assert result.command_name == "help"
    assert "Usage: `/model [set <provider/model>]`" in result.text
