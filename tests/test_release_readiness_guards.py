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
