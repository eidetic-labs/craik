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


def test_writer_coverage_guard_accepts_transitive_production_callers(
    tmp_path, monkeypatch
) -> None:
    store_dir = tmp_path / "src" / "craik" / "runtime" / "store"
    store_dir.mkdir(parents=True)
    (store_dir / "example.py").write_text(
        textwrap.dedent(
            """
            class ExampleStoreMixin:
                def put_live(self, value): ...
            """
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src" / "craik"
    (src / "channel_setup.py").write_text(
        textwrap.dedent(
            """
            def persist_live(store, value):
                store.put_live(value)
            """
        ),
        encoding="utf-8",
    )
    (src / "cli_widget.py").write_text(
        textwrap.dedent(
            """
            import typer

            app = typer.Typer()

            @app.command("setup")
            def setup() -> None:
                persist_live(store, "value")
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._extension_writer_call_failures() == []


def test_writer_coverage_guard_rejects_unreachable_wrapper(tmp_path, monkeypatch) -> None:
    store_dir = tmp_path / "src" / "craik" / "runtime" / "store"
    store_dir.mkdir(parents=True)
    (store_dir / "example.py").write_text(
        textwrap.dedent(
            """
            class ExampleStoreMixin:
                def put_dead(self, value): ...
            """
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src" / "craik"
    (src / "channel_setup.py").write_text(
        textwrap.dedent(
            """
            def persist_dead(store, value):
                store.put_dead(value)
            """
        ),
        encoding="utf-8",
    )
    (src / "cli_widget.py").write_text(
        textwrap.dedent(
            """
            import typer

            app = typer.Typer()

            @app.command("setup")
            def setup() -> None:
                pass
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._extension_writer_call_failures() == [
        "src/craik/runtime/store/example.py: "
        "craik.runtime.store.example.put_dead has no production caller"
    ]


def test_qualified_name_collision_detected(tmp_path, monkeypatch) -> None:
    store_dir = tmp_path / "src" / "craik" / "runtime" / "store"
    store_dir.mkdir(parents=True)
    (store_dir / "alpha.py").write_text(
        textwrap.dedent(
            """
            def put_foo(value): ...
            """
        ),
        encoding="utf-8",
    )
    (store_dir / "beta.py").write_text(
        textwrap.dedent(
            """
            def put_foo(value): ...
            """
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src" / "craik"
    (src / "cli_widget.py").write_text(
        textwrap.dedent(
            """
            import typer
            from craik.runtime.store.alpha import put_foo

            app = typer.Typer()

            @app.command("setup")
            def setup() -> None:
                put_foo("value")
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._extension_writer_call_failures() == [
        "src/craik/runtime/store/beta.py: "
        "craik.runtime.store.beta.put_foo has no production caller"
    ]


def test_import_alias_resolves_to_qualified_target(tmp_path, monkeypatch) -> None:
    store_dir = tmp_path / "src" / "craik" / "runtime" / "store"
    store_dir.mkdir(parents=True)
    (store_dir / "example.py").write_text(
        textwrap.dedent(
            """
            def put_alias(value): ...
            """
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src" / "craik"
    (src / "cli_widget.py").write_text(
        textwrap.dedent(
            """
            import typer
            from craik.runtime.store.example import put_alias as write_alias

            app = typer.Typer()

            @app.command("setup")
            def setup() -> None:
                write_alias("value")
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._extension_writer_call_failures() == []


def test_cli_auth_coverage_guard_includes_root_cli() -> None:
    paths = {path.name for path in check_release_readiness._cli_command_paths()}

    assert "cli.py" in paths


def test_cli_auth_coverage_guard_includes_cli_module_glob() -> None:
    paths = {path.name for path in check_release_readiness._cli_command_paths()}

    assert "cli_agents.py" in paths


def test_cli_auth_coverage_guard_scans_new_cli_modules(tmp_path, monkeypatch) -> None:
    src = tmp_path / "src" / "craik"
    src.mkdir(parents=True)
    (src / "cli_widget.py").write_text(
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
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    failures = check_release_readiness._cli_auth_coverage_failures()

    assert failures == [
        "src/craik/cli_widget.py: command `unsafe` touches LocalStore "
        "without operator_identity_or_fail()"
    ]


def test_cli_auth_exemption_surface_is_bounded() -> None:
    assert len(check_release_readiness.AUTH_EXEMPT_CLI_COMMANDS) <= 15


def test_registry_dispatched_allowlist_cap_enforced() -> None:
    assert len(check_release_readiness.REGISTRY_DISPATCHED_CALLABLES) <= 8


def test_registry_dispatched_allowlist_targets_real_functions() -> None:
    source_functions = check_release_readiness._source_function_qualnames()

    for qualname in check_release_readiness.REGISTRY_DISPATCHED_CALLABLES:
        assert qualname in source_functions


def test_dashboard_binding_token_not_emitted() -> None:
    root = Path(__file__).resolve().parents[1]
    scanned_paths = [
        root / "src" / "craik" / "cli_auth.py",
        *(root / "src" / "craik" / "runtime" / "companions").glob("*.py"),
    ]
    forbidden_keys = {"dashboard_binding_token"}

    for path in scanned_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            literal_keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            assert literal_keys.isdisjoint(forbidden_keys), path


def test_cli_auth_exemption_surface_matches_documented_bootstrap_commands() -> None:
    assert check_release_readiness.AUTH_EXEMPT_CLI_COMMANDS == {
        ("src/craik/cli_auth.py", "login"): (
            "bootstrap command; it creates the operator session required by auth-gated commands"
        ),
        ("src/craik/cli_auth.py", "logout"): (
            "bootstrap command; operators must be able to clear a stale or missing session"
        ),
        ("src/craik/cli_auth.py", "whoami"): (
            "session introspection command; it reports missing sessions without requiring one first"
        ),
        ("src/craik/cli_auth_login.py", "auth_login_provider"): (
            "provider credential bootstrap command; it captures provider credentials before "
            "an operator session may exist"
        ),
        ("src/craik/cli_auth_login.py", "auth_migrate_from_env"): (
            "one-time provider credential migration command; it runs during auth bootstrap"
        ),
        ("src/craik/cli_auth.py", "auth_list"): (
            "read-only provider credential diagnostic; usable before operator login"
        ),
        ("src/craik/cli_auth.py", "auth_status"): (
            "read-only provider credential diagnostic; usable before operator login"
        ),
        ("src/craik/cli_demos.py", "demo_persistent_agent"): (
            "deterministic demo uses fixture identity and is hardened separately "
            "from real agent commands"
        ),
        ("src/craik/cli_demos.py", "demo_stigmem_docs"): (
            "onboarding demo uses fixture-local state before an operator session exists; "
            "CRAIK_LIVE=1 provider transport is separately operator-session gated"
        ),
        ("src/craik/cli_onboarding.py", "onboard"): (
            "first-run bootstrap command that may execute before operator login is configured"
        ),
        ("src/craik/cli_operations.py", "policy_test"): (
            "deterministic release/security baseline run by CI before operator login exists"
        ),
        ("src/craik/cli_gateway.py", "gateway_install_command"): (
            "service-unit generation is offline preparation; no operator context required"
        ),
        ("src/craik/cli_gateway.py", "gateway_uninstall_command"): (
            "service-unit removal is offline preparation; no operator context required"
        ),
        ("src/craik/cli_gateway.py", "gateway_status_command"): (
            "service status inspection is read-only diagnostic; usable before operator login"
        ),
        ("src/craik/cli_gateway.py", "gateway_doctor_command"): (
            "gateway diagnostic is usable before operator login"
        ),
    }


def test_operator_login_remediation_guard_rejects_bare_auth_login(
    tmp_path, monkeypatch
) -> None:
    src = tmp_path / "src" / "craik"
    src.mkdir(parents=True)
    (src / "cli_widget.py").write_text(
        'MESSAGE = "active operator session required; run craik auth login"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._operator_login_remediation_failures() == [
        "src/craik/cli_widget.py:1: use `craik login` for "
        "operator-session remediation; reserve `craik auth login <provider>` "
        "for provider credentials"
    ]


def test_operator_login_remediation_guard_allows_provider_login(
    tmp_path, monkeypatch
) -> None:
    src = tmp_path / "src" / "craik"
    src.mkdir(parents=True)
    (src / "cli_widget.py").write_text(
        'MESSAGE = "run craik auth login <provider>"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._operator_login_remediation_failures() == []


def test_operator_login_remediation_guard_rejects_tui_cli_login(
    tmp_path, monkeypatch
) -> None:
    src = tmp_path / "src" / "craik" / "runtime" / "shell"
    src.mkdir(parents=True)
    (src / "readiness.py").write_text(
        'MESSAGE = "exit and run craik login"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._operator_login_remediation_failures() == [
        "src/craik/runtime/shell/readiness.py:1: use `/login` for "
        "operator-session remediation inside TUI surfaces"
    ]


def test_i18n_consumption_guard_rejects_unwired_surface(tmp_path, monkeypatch) -> None:
    surface = tmp_path / "src" / "craik" / "runtime" / "shell"
    surface.mkdir(parents=True)
    (surface / "agent_shell.py").write_text('MESSAGE = "Ready"\n', encoding="utf-8")
    monkeypatch.setattr(
        check_release_readiness,
        "I18N_REQUIRED_SURFACES",
        {"src/craik/runtime/shell/agent_shell.py": "shell messages"},
    )
    monkeypatch.setattr(check_release_readiness, "ROOT", tmp_path)

    assert check_release_readiness._i18n_consumption_failures() == [
        "src/craik/runtime/shell/agent_shell.py: "
        "does not consume localize() for shell messages"
    ]


def test_store_writer_exemption_surface_matches_documented_legacy_writers() -> None:
    assert check_release_readiness.STORE_WRITER_EXEMPTIONS == {
        "src/craik/runtime/store/memory.py": {
            "put_assumption": (
                "legacy direct-store API; assumptions are persisted through fixtures/tests"
            ),
        },
        "src/craik/runtime/store/work.py": {
            "put_capability_grant": (
                "legacy direct-store API; grant orchestration is still runtime-facing"
            ),
        },
    }
