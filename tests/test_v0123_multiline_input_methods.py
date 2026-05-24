from __future__ import annotations

from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_widgets.craik_input import (
    MULTILINE_HELP_TEXT,
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
