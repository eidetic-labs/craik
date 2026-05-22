import ast
import importlib.util
import textwrap
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_release_readiness.py"
_SPEC = importlib.util.spec_from_file_location("check_release_readiness", _SCRIPT)
assert _SPEC is not None
assert _SPEC.loader is not None
check_release_readiness = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_release_readiness)


def test_cli_auth_coverage_guard_reports_store_command_without_operator_auth() -> None:
    tree = ast.parse(
        textwrap.dedent(
            """
            import typer
            from craik.runtime.store import LocalStore

            app = typer.Typer()

            @app.command("unsafe")
            def unsafe() -> None:
                store = LocalStore.from_env()
                store.initialize()
            """
        )
    )
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))

    assert check_release_readiness._has_command_decorator(function)
    assert check_release_readiness._touches_local_store(function)
    assert not check_release_readiness._calls_operator_auth(function)


def test_cli_auth_coverage_guard_accepts_operator_auth() -> None:
    tree = ast.parse(
        textwrap.dedent(
            """
            import typer
            from craik.runtime.store import LocalStore

            app = typer.Typer()

            @app.command("safe")
            def safe() -> None:
                operator_identity_or_fail()
                store = LocalStore.from_env()
                store.initialize()
            """
        )
    )
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))

    assert check_release_readiness._has_command_decorator(function)
    assert check_release_readiness._touches_local_store(function)
    assert check_release_readiness._calls_operator_auth(function)


def test_writer_coverage_guard_scans_profile_store_writers() -> None:
    profile_store = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "craik"
        / "runtime"
        / "store"
        / "profiles.py"
    )

    assert "put_gateway_runtime_state" in check_release_readiness._store_writer_names(
        profile_store
    )


def test_cli_auth_coverage_guard_includes_root_cli() -> None:
    paths = {path.name for path in check_release_readiness._cli_command_paths()}

    assert "cli.py" in paths
