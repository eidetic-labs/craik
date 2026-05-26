"""Migration coverage for approvals and handoff command contract surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.reviewing.approval_commands import approvals_list_result
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_widgets.slash_renderers import (
    _empty_state_payload,
    render_slash_payload,
)
from craik.runtime.work.commands.handoff_commands import handoff_list_result


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def _slash_output(command: str, *, env: dict[str, str] | None = None) -> str:
    result = dispatch_slash_command(command, env=env)
    if result.empty_state_message is not None:
        return _capture(_empty_state_payload(result), width=80)
    assert result.payload is not None
    assert result.payload_shape is not None
    return _capture(render_slash_payload(result.payload, shape=result.payload_shape), width=80)


def test_approvals_and_handoffs_slash_share_helper_payloads(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    approvals = dispatch_slash_command("/approvals", env=env)
    handoffs = dispatch_slash_command("/handoffs", env=env)

    assert json.loads(approvals.text) == approvals_list_result(env=env).payload
    assert json.loads(handoffs.text) == handoff_list_result(env).payload


def test_approval_and_handoff_helpers_return_command_results(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    approvals = approvals_list_result(env=env)
    handoffs = handoff_list_result(env)

    assert isinstance(approvals, CommandResult)
    assert approvals.shape == "card_list"
    assert handoffs.shape == "card_list"
    assert approvals.payload == {"count": 0, "approvals": []}
    assert handoffs.payload == {"count": 0, "handoffs": []}


def test_approvals_and_handoff_commands_are_registered() -> None:
    import craik.cli_handoffs  # noqa: F401
    from craik.cli import app

    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/approvals") is not None
    assert registry.spec_by_name("/approvals-show") is not None
    assert registry.spec_by_name("/approvals-approve") is not None
    assert registry.spec_by_name("/approvals-deny") is not None
    assert registry.spec_by_name("/handoffs") is not None
    assert registry.spec_by_name("/handoff-create") is not None
    assert registry.spec_by_name("/handoff-show") is not None


def test_approvals_tui_snapshot(tmp_path: Path) -> None:
    output = _slash_output("/approvals", env={"CRAIK_HOME": str(tmp_path / "home")})
    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "approvals"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))


def test_handoffs_tui_snapshot(tmp_path: Path) -> None:
    output = _slash_output("/handoffs", env={"CRAIK_HOME": str(tmp_path / "home")})
    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "handoffs"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
