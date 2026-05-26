"""Regression tests for v0.12.8 CLI/TUI contract guard scripts."""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_command_result_return = _load_script("check_command_result_return")
check_no_direct_stdout = _load_script("check_no_direct_stdout")


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def test_no_direct_stdout_guard_catches_typer_json_echo(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/craik/cli_auth.py",
        """
        from craik.runtime.contract import CommandResult, craik_command
        import typer
        import json

        @craik_command(payload_shape="card_list")
        def auth_list() -> CommandResult:
            typer.echo(json.dumps({}))
            return CommandResult(payload={})
        """,
    )

    failures = check_no_direct_stdout.direct_stdout_failures(tmp_path)

    assert failures == [
        "src/craik/cli_auth.py:8 auth_list emits JSON directly; "
        "use craik.cli_output.emit_command_result(result)"
    ]


def test_no_direct_stdout_guard_catches_print_json(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/craik/cli_example.py",
        """
        import json
        from craik.runtime.contract import CommandResult, craik_command

        @craik_command(payload_shape="kv")
        def example_status() -> CommandResult:
            print(json.dumps({"ok": True}))
            return CommandResult(payload={})
        """,
    )

    failures = check_no_direct_stdout.direct_stdout_failures(tmp_path)

    assert failures == [
        "src/craik/cli_example.py:7 example_status emits JSON directly; "
        "use craik.cli_output.emit_command_result(result)"
    ]


def test_no_direct_stdout_guard_catches_sys_stdout_json_write(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/craik/cli_example.py",
        """
        import json
        import sys
        from craik.runtime.contract import CommandResult, craik_command

        @craik_command(payload_shape="kv")
        def example_status() -> CommandResult:
            sys.stdout.write(json.dumps({"ok": True}))
            return CommandResult(payload={})
        """,
    )

    failures = check_no_direct_stdout.direct_stdout_failures(tmp_path)

    assert failures == [
        "src/craik/cli_example.py:8 example_status emits JSON directly; "
        "use craik.cli_output.emit_command_result(result)"
    ]


def test_no_direct_stdout_guard_accepts_emit_helper(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/craik/cli_auth.py",
        """
        from craik.cli_output import emit_command_result
        from craik.runtime.contract import CommandResult, craik_command

        @craik_command(payload_shape="card_list")
        def auth_list() -> CommandResult:
            result = CommandResult(payload={})
            emit_command_result(result)
            return result
        """,
    )

    assert check_no_direct_stdout.direct_stdout_failures(tmp_path) == []


def test_no_direct_stdout_guard_catches_direct_json_echo_for_tui_commands(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/craik/cli_example.py",
        """
        import json
        import typer
        from craik.runtime.contract import CommandResult, craik_command

        @craik_command(payload_shape="kv")
        def example_status() -> CommandResult:
            result = CommandResult(payload={"ok": True})
            typer.echo(json.dumps(result.payload))
            return result
        """,
    )

    failures = check_no_direct_stdout.direct_stdout_failures(tmp_path)

    assert failures == [
        "src/craik/cli_example.py:9 example_status emits JSON directly; "
        "use craik.cli_output.emit_command_result(result)"
    ]


def test_no_direct_stdout_guard_allows_direct_json_echo_for_protocol_handlers(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/craik/cli_mcp.py",
        """
        import json
        import typer
        from craik.runtime.contract import craik_command

        @craik_command(tui_eligible=False, tui_exempt_reason="streams JSON-RPC stdout")
        def server_handle_command() -> None:
            typer.echo(json.dumps({"jsonrpc": "2.0"}))
        """,
    )

    assert check_no_direct_stdout.direct_stdout_failures(tmp_path) == []


def test_command_result_return_guard_catches_missing_annotation(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/craik/cli_example.py",
        """
        from craik.runtime.contract import craik_command

        @craik_command(payload_shape="kv")
        def status():
            return {}
        """,
    )

    failures = check_command_result_return.command_result_return_failures(tmp_path)

    assert failures == ["src/craik/cli_example.py:5 status must annotate -> CommandResult"]


def test_command_result_return_guard_skips_tui_exempt_protocol_handlers(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/craik/cli_mcp.py",
        """
        from craik.runtime.contract import craik_command

        @craik_command(tui_eligible=False, tui_exempt_reason="streams protocol stdout")
        def server_handle_command() -> None:
            return None
        """,
    )

    assert check_command_result_return.command_result_return_failures(tmp_path) == []


def test_contract_guards_pass_current_repo() -> None:
    root = Path(__file__).resolve().parents[1]

    assert check_no_direct_stdout.direct_stdout_failures(root) == []
    assert check_command_result_return.command_result_return_failures(root) == []
