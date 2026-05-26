from __future__ import annotations

from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_specs


def test_all_slash_command_specs_define_empty_state_guidance() -> None:
    missing = [spec.name for spec in get_tui_slash_specs() if spec.empty_state is None]

    assert missing == []
