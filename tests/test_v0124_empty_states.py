from __future__ import annotations

from craik.runtime.shell.slash_command_schema import slash_command_specs


def test_all_slash_command_specs_define_empty_state_guidance() -> None:
    missing = [spec.name for spec in slash_command_specs() if spec.empty_state is None]

    assert missing == []
