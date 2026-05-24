from __future__ import annotations

from craik.runtime.shell.slash_commands import dispatch_slash_command


def test_theme_rejects_invalid_choice_with_structured_guidance() -> None:
    result = dispatch_slash_command("/theme purple", env={})

    assert result.exit_code == 2
    assert "unknown theme `purple`" in result.text
    assert "`dark`" in result.text
    assert "`light`" in result.text
    assert "`monochrome`" in result.text


def test_model_set_rejects_invalid_selector_before_write() -> None:
    result = dispatch_slash_command("/model set openai", env={})

    assert result.exit_code == 2
    assert "provider/model selector" in result.text
    assert "Usage: `/model [set <provider/model>]`" in result.text


def test_resume_without_session_id_returns_argument_help() -> None:
    result = dispatch_slash_command("/resume", env={})

    assert result.exit_code == 0
    assert "Usage: `/resume <session-id>`" in result.text
    assert "Required arguments:" in result.text
