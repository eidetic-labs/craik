from pathlib import Path

import pytest
from typer.testing import CliRunner

from craik.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    "args",
    [
        ["operator", "overview"],
        ["operator", "work-graph"],
        ["operator", "handoff", "handoff_missing"],
        ["operator", "receipt", "receipt_missing"],
        ["operator", "contradictions"],
        ["operator", "evidence"],
        ["operator", "delegations"],
        ["operator", "budget"],
        ["operator", "instructions"],
        ["operator", "quality"],
        ["operator", "memory-impact", "preview_missing"],
        ["operator", "traps"],
        ["operator", "run-delta", "run_delta_missing"],
    ],
)
def test_operator_commands_require_active_session(
    tmp_path: Path,
    args: list[str],
) -> None:
    result = runner.invoke(app, args, env={"CRAIK_HOME": str(tmp_path / "home")})

    assert result.exit_code == 2
    assert "active operator session required; run craik auth login" in result.output
