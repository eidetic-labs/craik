from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import AgentSessionState
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.dashboard import (
    DashboardConfig,
    DashboardConfigError,
    dashboard_preview_payload,
    handle_dashboard_request,
    validate_dashboard_config,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_dashboard_requires_token_or_operator_session(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    config = DashboardConfig(auth_token=None)

    with pytest.raises(DashboardConfigError, match="operator session or --auth-token"):
        validate_dashboard_config(config, env=env)

    token_config = DashboardConfig(auth_token="dashboard-token")
    assert validate_dashboard_config(token_config, env=env) == []


def test_dashboard_rejects_nonlocal_bind_without_override(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    config = DashboardConfig(host="0.0.0.0", auth_token="dashboard-token")

    with pytest.raises(DashboardConfigError, match="non-local dashboard bind"):
        validate_dashboard_config(config, env=env)

    warnings = validate_dashboard_config(
        DashboardConfig(host="0.0.0.0", auth_token="dashboard-token", allow_unsafe_bind=True),
        env=env,
    )
    assert warnings == [
        "Dashboard is bound outside localhost; place it behind local-only access controls."
    ]


def test_dashboard_routes_require_and_accept_token(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    config = DashboardConfig(auth_token="dashboard-token")

    denied = handle_dashboard_request("GET", "/status", {}, b"", config, env=env)
    accepted = handle_dashboard_request(
        "GET",
        "/status",
        {"X-Craik-Dashboard-Token": "dashboard-token"},
        b"",
        config,
        env=env,
    )

    assert denied.status == 401
    assert accepted.status == 200
    assert accepted.content_type.startswith("text/html")
    assert b"Status" in accepted.body
    assert b"state: unconfigured" in accepted.body


def test_dashboard_active_operator_session_authorizes_without_token(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)
    config = DashboardConfig(auth_token=None)

    response = handle_dashboard_request("GET", "/api/status", {}, b"", config, env=env)
    payload = json.loads(response.body)

    assert response.status == 200
    assert payload["readiness"]["operator_authenticated"] is True


def test_dashboard_status_counts_sessions_and_redacts_secret_like_text(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    try:
        store.initialize()
        store.put_agent_session_state(
            AgentSessionState(
                id="agent_session_dashboard",
                project_id="project_dashboard",
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
    config = DashboardConfig(auth_token="dashboard-token")

    response = handle_dashboard_request(
        "GET",
        "/api/status?token=dashboard-token",
        {},
        b"",
        config,
        env=env | {"CRAIK_PROFILE": "token=secret-value"},
    )
    payload = json.loads(response.body)

    assert payload["counts"]["sessions"] == 1
    assert "secret-value" not in response.body.decode("utf-8")
    assert "[REDACTED]" in response.body.decode("utf-8")


def test_dashboard_action_dispatch_uses_shared_slash_registry(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    config = DashboardConfig(auth_token="dashboard-token")

    response = handle_dashboard_request(
        "POST",
        "/api/actions",
        {"Authorization": "Bearer dashboard-token"},
        json.dumps({"command": "/help status"}).encode("utf-8"),
        config,
        env=env,
    )
    payload = json.loads(response.body)

    assert response.status == 200
    assert payload["command"] == "/help status"
    assert "Usage: /status" in payload["text"]


def test_dashboard_cli_dry_run_reports_non_secret_launch_metadata(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home"), "CRAIK_DASHBOARD_TOKEN": "dashboard-token"}

    result = runner.invoke(app, ["dashboard", "--dry-run"], env=env)
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["auth"] == "token"
    assert payload["host"] == "127.0.0.1"
    assert payload["url"] == "http://127.0.0.1:8787/"


def test_dashboard_preview_uses_operator_session_when_no_token(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)

    payload = dashboard_preview_payload(DashboardConfig(auth_token=None), env=env)

    assert payload["auth"] == "operator-session"
    assert payload["url"] == "http://127.0.0.1:8787/"


def _put_operator_session(home: Path) -> None:
    store = OperatorSessionStore(home)
    store.put(
        OperatorSession(
            subject="operator:test",
            email="operator@example.invalid",
            display_name="Operator Test",
            groups=["maintainers"],
            issuer="https://issuer.example.invalid",
            id_token_jti="jti-dashboard",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
