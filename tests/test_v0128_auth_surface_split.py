from __future__ import annotations

import ast
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_v0128_auth_modules_are_both_loaded_by_root_cli() -> None:
    source = (ROOT / "src" / "craik" / "cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    loaded_modules = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert "craik.cli_auth" in loaded_modules
    assert "craik.cli_auth_login" in loaded_modules


def test_v0128_auth_surface_keeps_profile_and_login_commands() -> None:
    result = runner.invoke(app, ["auth", "--help"])

    assert result.exit_code == 0, result.output
    for command in [
        "add",
        "list",
        "login",
        "logout",
        "migrate-from-env",
        "status",
        "storage",
    ]:
        assert command in result.output


def test_v0128_operator_session_commands_remain_top_level() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "login" in result.output
    assert "logout" in result.output
    assert "whoami" in result.output
