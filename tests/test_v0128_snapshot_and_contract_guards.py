"""Regression tests for v0.12.8 snapshot and CLI/TUI contract helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import typer

from craik.runtime.contract import CommandResult, craik_command

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_cli_tui_contract = _load_script("check_cli_tui_contract")
generate_snapshots = _load_script("generate_snapshots")


def test_cli_tui_contract_guard_detects_duplicate_slash_aliases() -> None:
    app = typer.Typer()

    @app.command("alpha")
    @craik_command(slash_alias="same", payload_shape="kv")
    def alpha() -> CommandResult:
        return CommandResult(payload={"alpha": True}, shape="kv")

    @app.command("beta")
    @craik_command(slash_alias="same", payload_shape="kv")
    def beta() -> CommandResult:
        return CommandResult(payload={"beta": True}, shape="kv")

    registry = check_cli_tui_contract.registry_from_app(app)

    assert check_cli_tui_contract.cli_tui_contract_failures(registry) == [
        "/same: duplicate slash name maps to 2 callbacks"
    ]


def test_cli_tui_contract_guard_accepts_current_registry() -> None:
    from craik.cli import app

    registry = check_cli_tui_contract.registry_from_app(app)

    assert check_cli_tui_contract.cli_tui_contract_failures(registry) == []


def test_snapshot_writer_creates_expected_width_files(tmp_path: Path) -> None:
    snapshots = {
        60: "narrow\n",
        80: "wide\n",
    }

    failures = generate_snapshots.write_or_check_snapshots(
        snapshots,
        output_root=tmp_path,
        name="status",
        check=False,
    )

    assert failures == []
    assert (tmp_path / "status" / "width-60.txt").read_text(encoding="utf-8") == "narrow\n"
    assert (tmp_path / "status" / "width-80.txt").read_text(encoding="utf-8") == "wide\n"


def test_snapshot_check_reports_missing_and_stale_files(tmp_path: Path) -> None:
    target = tmp_path / "status"
    target.mkdir()
    (target / "width-60.txt").write_text("old\n", encoding="utf-8")

    failures = generate_snapshots.write_or_check_snapshots(
        {
            60: "new\n",
            80: "wide\n",
        },
        output_root=tmp_path,
        name="status",
        check=True,
    )

    assert len(failures) == 2
    assert failures[0].endswith("width-60.txt is stale")
    assert failures[1].endswith("width-80.txt is missing")


def test_snapshot_name_uses_first_slash_token() -> None:
    assert generate_snapshots._snapshot_name("/model set openai/gpt-5") == "model"
