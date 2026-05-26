"""Regression tests for v0.12.8 snapshot and CLI/TUI contract helpers."""

from __future__ import annotations

import importlib.util
import textwrap
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
check_format_flag_coverage = _load_script("check_format_flag_coverage")
check_modal_screen_mappings = _load_script("check_modal_screen_mappings")
check_next_actions_validity = _load_script("check_next_actions_validity")
check_payload_shape_validity = _load_script("check_payload_shape_validity")
check_snapshot_coverage = _load_script("check_snapshot_coverage")
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


def test_payload_shape_validity_guard_accepts_current_cli_metadata() -> None:
    assert check_payload_shape_validity.payload_shape_validity_failures(ROOT) == []


def test_payload_shape_validity_guard_rejects_unknown_shape(tmp_path: Path) -> None:
    target = tmp_path / "src" / "craik"
    target.mkdir(parents=True)
    (target / "cli_bad.py").write_text(
        textwrap.dedent(
            """
        from craik.runtime.contract import craik_command

        @craik_command(payload_shape="spreadsheet")
        def bad_command():
            pass
        """
        ),
        encoding="utf-8",
    )

    failures = check_payload_shape_validity.payload_shape_validity_failures(tmp_path)

    assert failures == [
        "src/craik/cli_bad.py:4 payload_shape='spreadsheet' is not legal; "
        "expected one of ['auto', 'card', 'card_list', 'kv', 'markdown', 'table', 'tree']"
    ]


def test_next_action_validity_guard_accepts_current_source() -> None:
    slash_names = check_next_actions_validity._registered_slash_names()

    assert check_next_actions_validity.next_action_validity_failures(
        ROOT,
        slash_names,
    ) == []


def test_next_action_validity_guard_rejects_unknown_slash(tmp_path: Path) -> None:
    target = tmp_path / "src" / "craik" / "runtime"
    target.mkdir(parents=True)
    (target / "actions.py").write_text(
        textwrap.dedent(
            """
        from craik.runtime.contract import NextAction

        ACTION = NextAction(text="Do it", command="/missing now", field="status")
        """
        ),
        encoding="utf-8",
    )

    failures = check_next_actions_validity.next_action_validity_failures(
        tmp_path,
        slash_names={"/status"},
    )

    assert failures == [
        "src/craik/runtime/actions.py:4 NextAction.command='/missing now' "
        "does not resolve to a registered slash command"
    ]


def test_format_coverage_guard_accepts_current_contract_tests() -> None:
    assert check_format_flag_coverage.format_coverage_failures(ROOT) == []


def test_format_coverage_guard_reports_missing_text_test(tmp_path: Path) -> None:
    output = tmp_path / "src" / "craik"
    tests = tmp_path / "tests" / "contract"
    output.mkdir(parents=True)
    tests.mkdir(parents=True)
    (output / "cli_output.py").write_text(
        textwrap.dedent(
            """
        import typer

        def emit_command_result(result):
            output_format = detect_default_format()
            if output_format == "json":
                return "{}"
            rendered = format_command_result(result, kind=output_format)
            typer.echo(rendered)
        """
        ),
        encoding="utf-8",
    )
    (tests / "test_format.py").write_text(
        textwrap.dedent(
            """
        def test_detect_default_format_tty():
            pass

        def test_detect_default_format_non_tty():
            pass

        def test_json_format():
            format_command_result(object(), kind="json")

        def test_tui_format():
            format_command_result(object(), kind="tui")
        """
        ),
        encoding="utf-8",
    )

    failures = check_format_flag_coverage.format_coverage_failures(tmp_path)

    assert failures == [
        "tests/contract/test_format.py: missing format_command_result kind='text' test"
    ]


def test_modal_mapping_guard_accepts_current_prompt_metadata() -> None:
    assert check_modal_screen_mappings.prompt_metadata_failures(ROOT) == []


def test_modal_mapping_guard_rejects_unmapped_prompt_call(tmp_path: Path) -> None:
    target = tmp_path / "src" / "craik"
    target.mkdir(parents=True)
    (target / "cli_bad.py").write_text(
        textwrap.dedent(
            """
        import typer
        from craik.runtime.contract import craik_command

        @craik_command(payload_shape="card")
        def bad_command():
            typer.confirm("Proceed?")
        """
        ),
        encoding="utf-8",
    )

    failures = check_modal_screen_mappings.prompt_metadata_failures(tmp_path)

    assert failures == [
        "src/craik/cli_bad.py:6 bad_command uses typer prompt/confirm "
        "without interactive_prompts metadata"
    ]


def test_cli_tui_contract_guard_requires_legacy_marker(tmp_path: Path) -> None:
    target = tmp_path / "src" / "craik"
    target.mkdir(parents=True)
    (target / "cli_auth.py").write_text(
        textwrap.dedent(
            """
        import typer
        from craik.cli import app

        @app.command("login")
        def login() -> None:
            typer.echo("legacy")
        """
        ),
        encoding="utf-8",
    )
    for name in ("cli_shell.py", "cli_onboarding.py", "cli_status.py"):
        (target / name).write_text("", encoding="utf-8")

    failures = check_cli_tui_contract.legacy_command_marker_failures(tmp_path)

    assert failures == [
        "src/craik/cli_auth.py:6 login is a Typer command without "
        "@craik_command or craik-legacy-command: marker"
    ]


def test_cli_tui_contract_guard_accepts_marked_legacy_command(tmp_path: Path) -> None:
    target = tmp_path / "src" / "craik"
    target.mkdir(parents=True)
    (target / "cli_auth.py").write_text(
        textwrap.dedent(
            """
        import typer
        from craik.cli import app

        # craik-legacy-command: fixture legacy flow
        @app.command("login")
        def login() -> None:
            typer.echo("legacy")
        """
        ),
        encoding="utf-8",
    )
    for name in ("cli_shell.py", "cli_onboarding.py", "cli_status.py"):
        (target / name).write_text("", encoding="utf-8")

    assert check_cli_tui_contract.legacy_command_marker_failures(tmp_path) == []


def test_snapshot_coverage_guard_accepts_current_slash_specs() -> None:
    from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_specs

    assert (
        check_snapshot_coverage.snapshot_coverage_failures(
            check_snapshot_coverage.specs_with_snapshot_baselines(
                get_tui_slash_specs(),
                snapshot_root=ROOT / "tests" / "snapshots" / "slash",
            ),
            snapshot_root=ROOT / "tests" / "snapshots" / "slash",
        )
        == []
    )


def test_snapshot_coverage_guard_reports_missing_snapshot(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "width-80.txt").write_text("ok\n", encoding="utf-8")

    failures = check_snapshot_coverage.snapshot_coverage_failures(
        ["alpha", "beta"],
        snapshot_root=tmp_path,
    )

    assert failures == ["/beta: missing beta/width-80.txt"]


def test_snapshot_coverage_guard_requires_full_widths_for_table_specs(tmp_path: Path) -> None:
    from craik.runtime.shell.slash_command_schema import SlashCommandSpec

    target = tmp_path / "alpha"
    target.mkdir()
    (target / "width-80.txt").write_text("ok\n", encoding="utf-8")

    failures = check_snapshot_coverage.snapshot_coverage_failures(
        [
            SlashCommandSpec(
                name="/alpha",
                summary="Alpha.",
                usage="/alpha",
                payload_shape="table",
                help="Alpha.",
            )
        ],
        snapshot_root=tmp_path,
    )

    assert failures == [
        "/alpha: missing alpha/width-60.txt",
        "/alpha: missing alpha/width-100.txt",
        "/alpha: missing alpha/width-120.txt",
        "/alpha: missing alpha/width-160.txt",
        "/alpha: missing alpha/width-200.txt",
    ]


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


def test_snapshot_generator_can_seed_operator_session(tmp_path: Path) -> None:
    from craik.runtime.auth.operator import OperatorSessionStore

    generate_snapshots._seed_operator_session(tmp_path)

    session = OperatorSessionStore(tmp_path).get()
    assert session.subject == "snapshot-operator"
