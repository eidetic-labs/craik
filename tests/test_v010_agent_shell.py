import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import AgentSessionState
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command, list_slash_commands
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_default_craik_launches_shell_status_before_auth(tmp_path: Path) -> None:
    result = runner.invoke(app, [], env={"CRAIK_HOME": str(tmp_path / "home")})

    assert result.exit_code == 0
    assert "Craik Agent Shell" in result.output
    assert "State: unconfigured" in result.output
    assert "run /auth login or craik auth login" in result.output


def test_one_shot_is_quiet_and_reports_missing_readiness(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["-z", "Summarize readiness"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert result.output.startswith("Craik is not fully ready")
    assert "Craik Agent Shell" not in result.output


def test_status_command_and_slash_status_share_readiness(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    cli_status = runner.invoke(app, ["status"], env=env)
    slash_status = runner.invoke(app, ["slash", "/status"], env=env)

    assert cli_status.exit_code == 0
    assert slash_status.exit_code == 0
    assert json.loads(cli_status.stdout)["state"] == json.loads(slash_status.stdout)["state"]


def test_readiness_transitions_from_operator_only_to_fully_ready(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)

    assert resolve_readiness(env).state == "operator-only"

    login = runner.invoke(app, ["auth", "login", "openai", "--dry-run"], env=env)
    assert login.exit_code == 0
    assert json.loads(login.stdout)["dry_run"] is True

    login_write = runner.invoke(
        app,
        ["auth", "login", "openai", "--no-browser"],
        env=env,
    )
    model_set = runner.invoke(app, ["model", "set", "openai/gpt-5"], env=env)

    assert login_write.exit_code == 0
    assert model_set.exit_code == 0
    assert resolve_readiness(env).state == "fully-ready"


def test_slash_help_and_unknown_suggestion(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    assert any(command.name == "provider" for command in list_slash_commands())
    help_result = dispatch_slash_command("/help provider", env=env)
    unknown_result = dispatch_slash_command("/stats", env=env)

    assert "Usage: /provider" in help_result.text
    assert "unknown slash command" in unknown_result.text
    assert "/status" in unknown_result.text


def test_model_profile_session_and_usage_commands(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    try:
        store.initialize()
        store.put_agent_session_state(
            AgentSessionState(
                id="agent_session_docs",
                project_id="project_docs",
                operator_subject="operator:test",
                provider_id="openai",
                model_id="gpt-5",
                mode="interactive",
                status="idle",
                started_at=now,
                last_activity_at=now,
                updated_at=now,
            )
        )
    finally:
        store.close()

    assert runner.invoke(app, ["model", "set", "openai/gpt-5"], env=env).exit_code == 0
    model_status = runner.invoke(app, ["model", "status"], env=env)
    profile_create = runner.invoke(
        app,
        ["profile", "create", "release", "--description", "Release work"],
        env=env,
    )
    profile_use = runner.invoke(app, ["profile", "use", "release"], env=env)
    sessions = runner.invoke(app, ["session", "list"], env=env)
    session_export = runner.invoke(app, ["session", "export", "agent_session_docs"], env=env)
    usage = runner.invoke(app, ["usage"], env=env)

    assert json.loads(model_status.stdout)["active_model"] == "openai/gpt-5"
    assert profile_create.exit_code == 0
    assert profile_use.exit_code == 0
    assert json.loads(sessions.stdout)[0]["id"] == "agent_session_docs"
    assert json.loads(session_export.stdout)["redacted"] is True
    assert json.loads(usage.stdout)["token_usage"] == "unknown"


def test_auth_storage_status_is_redacted(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["auth", "storage", "status"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload) == {"backend", "secure", "status", "warning"}


def _put_operator_session(home: Path) -> None:
    ensure_craik_home({"CRAIK_HOME": str(home)})
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator:test",
            email="operator@example.test",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime(2026, 5, 22, 13, 0, tzinfo=UTC),
        )
    )
