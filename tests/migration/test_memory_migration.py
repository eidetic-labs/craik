"""Migration coverage for memory command contract surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result
from craik.runtime.memory.commands import (
    memory_diff_result,
    memory_list_result,
    memory_overview_result,
    memory_preview_result,
    memory_search_result,
)
from craik.runtime.shell.slash_commands import dispatch_slash_command


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_memory_slash_shares_overview_payload(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    slash = dispatch_slash_command("/memory", env=env)

    assert json.loads(slash.text) == memory_overview_result(env).payload


def test_memory_helpers_return_command_results(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    overview = memory_overview_result(env)
    listing = memory_list_result(env=env)
    search = memory_search_result("", env=env)
    diff = memory_diff_result("task_1", env=env)
    preview = memory_preview_result("task_1", env=env)

    assert isinstance(overview, CommandResult)
    assert overview.shape == "card_list"
    assert listing.payload == []
    assert search.payload == []
    assert diff.shape == "card"
    assert preview.shape == "card"


def test_memory_commands_are_registered() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/memory-list") is not None
    assert registry.spec_by_name("/memory-propose") is not None
    assert registry.spec_by_name("/memory-show") is not None
    assert registry.spec_by_name("/memory-approve") is not None
    assert registry.spec_by_name("/memory-reject") is not None
    assert registry.spec_by_name("/memory-search") is not None
    assert registry.spec_by_name("/memory-diff") is not None
    assert registry.spec_by_name("/memory-preview") is not None


def test_memory_tui_snapshot() -> None:
    output = _capture(
        format_command_result(
            CommandResult(
                payload={"proposals": [], "diffs": [], "impact_previews": []},
                shape="card_list",
            ),
            kind="tui",
        ),
        width=80,
    )

    snapshot = (
        Path(__file__).resolve().parents[1]
        / "snapshots"
        / "slash"
        / "memory"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
