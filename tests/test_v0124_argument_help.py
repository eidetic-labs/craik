from __future__ import annotations

from craik.runtime.shell.slash_command_schema.detail_help import command_detail_help


def test_action_key_help_renders_slash_alias() -> None:
    help_text = command_detail_help("approvals", env={})

    assert "`/`=focus-search" in help_text
    assert "`slash`=focus-search" not in help_text
