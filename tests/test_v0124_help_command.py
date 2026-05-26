from __future__ import annotations

from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_specs
from craik.runtime.shell.slash_commands import dispatch_slash_command


def test_help_without_args_renders_markdown_index() -> None:
    result = dispatch_slash_command("/help")

    assert result.command_name == "help"
    assert result.payload_shape == "markdown"
    assert "##" in result.text
    assert "`/provider`" in result.text
    assert "`/clear`" in result.text


def test_help_with_command_renders_detail_page() -> None:
    result = dispatch_slash_command("/help /provider")

    assert result.command_name == "help"
    assert "## /provider" in result.text
    assert "Inspect or configure provider credentials" in result.text
    assert "Usage: /provider [login <provider>]" in result.text
    assert "Output: `table`" in result.text
    assert "Examples:" in result.text


def test_help_accepts_bare_command_name() -> None:
    result = dispatch_slash_command("/help clear")

    assert "## /clear" in result.text
    assert "Confirmation: required." in result.text
    assert "Persisted receipts" in result.text


def test_help_unknown_command_suggests_near_match() -> None:
    result = dispatch_slash_command("/help provder")

    assert "No such slash command" in result.text
    assert "`/provider`" in result.text


def test_all_registered_commands_have_detail_pages() -> None:
    for spec in get_tui_slash_specs():
        result = dispatch_slash_command(f"/help {spec.name}")

        assert f"## {spec.name}" in result.text
        assert "Usage:" in result.text
        assert "Output:" in result.text
