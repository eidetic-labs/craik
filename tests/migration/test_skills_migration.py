"""Migration coverage for skills command contract surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from craik.cli import app
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.format import format_command_result
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.skills.commands import (
    skills_eval_result,
    skills_history_result,
    skills_overview_result,
    skills_promote_result,
    skills_proposals_result,
    skills_rollback_result,
    skills_telemetry_result,
)


def _capture(renderable: Any, *, width: int = 80) -> str:
    console = Console(color_system=None, force_terminal=False, record=True, width=width)
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def test_skills_slash_shares_overview_payload(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    slash = dispatch_slash_command("/skills", env=env)

    assert json.loads(slash.text) == skills_overview_result(env).payload


def test_skills_helpers_return_command_results(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    overview = skills_overview_result(env)
    telemetry = skills_telemetry_result(env)
    proposals = skills_proposals_result(env)
    evals = skills_eval_result(env=env)
    history = skills_history_result(env)
    promote = skills_promote_result("proposal_1")
    rollback = skills_rollback_result("package_1")

    assert isinstance(overview, CommandResult)
    assert overview.shape == "card_list"
    assert telemetry.payload["telemetry_count"] == 0
    assert proposals.payload["proposal_count"] == 0
    assert evals.payload["package_count"] == 0
    assert history.payload["packages"] == []
    assert promote.shape == "card"
    assert rollback.shape == "card"


def test_skills_commands_are_registered() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/skills-list") is not None
    assert registry.spec_by_name("/skills-install") is not None
    assert registry.spec_by_name("/skills-enable") is not None
    assert registry.spec_by_name("/skills-disable") is not None
    assert registry.spec_by_name("/skills-show") is not None
    assert registry.spec_by_name("/skills-telemetry") is not None
    assert registry.spec_by_name("/skills-proposals") is not None
    assert registry.spec_by_name("/skills-eval") is not None
    assert registry.spec_by_name("/skills-promote") is not None
    assert registry.spec_by_name("/skills-rollback") is not None
    assert registry.spec_by_name("/skills-history") is not None


def test_skills_tui_snapshot() -> None:
    output = _capture(
        format_command_result(
            CommandResult(
                payload={"packages": [], "registries": [], "proposals": []},
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
        / "skills"
        / "width-80.txt"
    )
    assert _rstrip_lines(output) == _rstrip_lines(snapshot.read_text(encoding="utf-8"))
