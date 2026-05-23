from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth import AuthProfile, AuthProfileStore, CredentialKind
from craik.runtime.auth.login import profile_runtime_status
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.dashboard import DashboardConfig
from craik.runtime.dashboard.server import handle_dashboard_request, validate_dashboard_config
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command, slash_command_is_mutating
from craik.runtime.shell.tui import build_tui_snapshot, render_tui_snapshot

runner = CliRunner()


def test_auth_login_captures_keyring_ref_without_leaking_secret(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home), "CRAIK_CREDENTIAL_BACKEND": "file"}

    result = runner.invoke(
        app,
        ["auth", "login", "openai", "--no-browser", "--json"],
        input="sk-test-captured\n",
        env=env,
    )

    assert result.exit_code == 0, result.output
    assert "sk-test-captured" not in result.output
    payload = _json_payload(result.stdout)
    assert payload["kind"] == "keyring-ref"
    assert payload["credential_storage"]["backend"] == "file"
    profile = AuthProfileStore(home).get("openai:default")
    assert profile.kind is CredentialKind.KEYRING_REF
    assert profile.metadata["ref"] == "openai:default:api-key"
    assert profile_runtime_status(profile, env=env).status == "ok"


def test_auth_login_rejected_key_uses_redacted_remediation(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home"), "CRAIK_CREDENTIAL_BACKEND": "file"}

    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--no-browser", "--json"],
        input="bad key with spaces\n",
        env=env,
    )

    assert result.exit_code == 0, result.output
    assert "bad key" not in result.output
    payload = _json_payload(result.stdout)
    assert payload["status"]["status"] == "rejected"
    assert payload["status"]["detail"] == (
        "Your Anthropic key was rejected. Re-run craik auth login anthropic."
    )
    assert AuthProfileStore(tmp_path / "home").list() == []


def test_auth_status_and_logout_require_operator_and_remove_cache(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home), "CRAIK_CREDENTIAL_BACKEND": "file"}
    login = runner.invoke(
        app,
        ["auth", "login", "gemini", "--no-browser", "--json"],
        input="gemini-key\n",
        env=env,
    )
    assert login.exit_code == 0, login.output

    unauthenticated = runner.invoke(app, ["auth", "status"], env=env)
    _put_session(home)
    status = runner.invoke(app, ["auth", "status"], env=env)
    logout = runner.invoke(app, ["auth", "logout", "gemini"], env=env)
    status_after = resolve_readiness(env)

    assert unauthenticated.exit_code != 0
    assert "active operator session required" in unauthenticated.output
    status_payload = json.loads(status.stdout)
    assert status_payload[0]["kind"] == "keyring-ref"
    assert status_payload[0]["backend"] == "file"
    assert status_payload[0]["health_status"] == "ok"
    assert json.loads(logout.stdout)["removed_keyring_ref"] is True
    assert AuthProfileStore(home).list() == []
    assert status_after.provider_configured is False


def test_migrate_from_env_is_consent_based_and_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {
        "CRAIK_HOME": str(home),
        "CRAIK_CREDENTIAL_BACKEND": "file",
        "CRAIK_OPENAI_API_KEY": "env-secret",
    }
    AuthProfileStore(home).put(
        AuthProfile(
            id="openai:default",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "CRAIK_OPENAI_API_KEY"},
            created_at=datetime.now(UTC),
        )
    )

    dry_run = runner.invoke(app, ["auth", "migrate-from-env", "--dry-run", "--yes"], env=env)
    applied = runner.invoke(app, ["auth", "migrate-from-env", "--apply", "--yes"], env=env)
    second = runner.invoke(app, ["auth", "migrate-from-env", "--apply", "--yes"], env=env)

    assert dry_run.exit_code == 0, dry_run.output
    assert json.loads(dry_run.stdout)["migrated"][0]["dry_run"] is True
    assert applied.exit_code == 0, applied.output
    profile = AuthProfileStore(home).get("openai:default")
    assert profile.kind is CredentialKind.KEYRING_REF
    assert "env_var" not in profile.metadata
    assert json.loads(second.stdout)["migrated"] == []
    assert json.loads(second.stdout)["skipped"][0]["reason"] == "not-env-var-profile"


def test_readiness_uses_credential_resolvability(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    AuthProfileStore(home).put(
        AuthProfile(
            id="openai:default",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "MISSING_OPENAI_API_KEY"},
            created_at=datetime.now(UTC),
        )
    )

    assert resolve_readiness(env).provider_configured is False


def test_slash_tui_and_dashboard_auth_status_surfaces(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home), "CRAIK_CREDENTIAL_BACKEND": "file"}
    login = runner.invoke(
        app,
        ["auth", "login", "local", "--no-browser", "--json"],
        input="local-key\n",
        env=env,
    )
    assert login.exit_code == 0, login.output
    _put_session(home)

    slash = dispatch_slash_command("/auth status", env=env)
    tui = render_tui_snapshot(build_tui_snapshot(env))
    config = DashboardConfig(auth_token="token")
    dashboard = handle_dashboard_request(
        "GET",
        "/api/auth",
        {"X-Craik-Dashboard-Token": "token"},
        b"",
        config,
        env=env,
    )

    assert slash_command_is_mutating("/auth status") is False
    assert json.loads(slash.text)[0]["health_status"] == "ok"
    assert "Auth" in tui
    assert "chat_completions:local" in tui
    assert dashboard.status == 200
    assert json.loads(dashboard.body)["auth"][0]["id"] == "chat_completions:local"
    assert validate_dashboard_config(config, env=env) == []


def _put_session(home: Path) -> None:
    session = OperatorSession(
        subject="operator-123",
        email="operator@example.test",
        display_name="Operator",
        groups=["platform"],
        issuer="https://issuer.example.test",
        id_token_jti="token-1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_token_ref="operator-session.refresh_token",
    )
    OperatorSessionStore(home).put(session, refresh_token="refresh-token")


def _json_payload(output: str) -> dict[str, object]:
    return json.loads(output[output.index("{") :])
