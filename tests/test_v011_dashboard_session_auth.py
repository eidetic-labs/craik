from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.dashboard import (
    DashboardConfig,
    dashboard_preview_payload,
    handle_dashboard_request,
)
from craik.runtime.paths import ensure_craik_home


def test_dashboard_operator_session_mode_requires_session_header(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    ensure_craik_home(env)
    _put_operator_session(home)
    config = DashboardConfig(auth_token=None)

    missing = handle_dashboard_request("GET", "/api/status", {}, b"", config, env=env)
    wrong = handle_dashboard_request(
        "GET",
        "/api/status",
        {"X-Craik-Operator-Session": "wrong-session"},
        b"",
        config,
        env=env,
    )
    accepted = handle_dashboard_request(
        "GET",
        "/api/status",
        {"X-Craik-Operator-Session": "dashboard-binding-token"},
        b"",
        config,
        env=env,
    )

    assert missing.status == 401
    assert wrong.status == 401
    assert accepted.status == 200
    assert json.loads(accepted.body)["readiness"]["operator_authenticated"] is True


def test_dashboard_rejects_jti_as_session_token(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    ensure_craik_home(env)
    _put_operator_session(home)
    config = DashboardConfig(auth_token=None)

    result = handle_dashboard_request(
        "GET",
        "/api/status",
        {"X-Craik-Operator-Session": "jti-dashboard"},
        b"",
        config,
        env=env,
    )

    assert result.status == 401


def test_dashboard_accepts_binding_token(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    ensure_craik_home(env)
    _put_operator_session(home)
    config = DashboardConfig(auth_token=None)

    result = handle_dashboard_request(
        "GET",
        "/api/status",
        {"X-Craik-Operator-Session": "dashboard-binding-token"},
        b"",
        config,
        env=env,
    )

    assert result.status == 200


def test_session_without_binding_token_forces_relogin(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    ensure_craik_home(env)
    _put_operator_session(home, dashboard_binding_token=None)
    config = DashboardConfig(auth_token=None)

    result = handle_dashboard_request(
        "GET",
        "/api/status",
        {"X-Craik-Operator-Session": "jti-dashboard"},
        b"",
        config,
        env=env,
    )
    payload = json.loads(result.body)

    assert result.status == 401
    assert payload["remediation"] == "stale session, re-login required"


def test_whoami_payload_omits_jti_and_binding_token() -> None:
    cli_auth = Path(__file__).resolve().parents[1] / "src" / "craik" / "cli_auth.py"
    tree = ast.parse(cli_auth.read_text(encoding="utf-8"), filename=str(cli_auth))
    payload_function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_operator_session_payload"
    )
    literal_keys = {
        key.value
        for node in ast.walk(payload_function)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }

    assert "id_token_jti" not in literal_keys
    assert "dashboard_binding_token" not in literal_keys


def test_dashboard_preview_warns_about_operator_session_header(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    ensure_craik_home(env)
    _put_operator_session(home)

    payload = dashboard_preview_payload(DashboardConfig(auth_token=None), env=env)

    assert payload["auth"] == "operator-session"
    assert payload["warnings"] == [
        "Operator-session dashboard auth requires X-Craik-Operator-Session bound "
        "to the active session."
    ]


def _put_operator_session(
    home: Path,
    *,
    dashboard_binding_token: str | None = "dashboard-binding-token",
) -> None:
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator:test",
            email="operator@example.invalid",
            display_name="Operator Test",
            groups=["maintainers"],
            issuer="https://issuer.example.invalid",
            id_token_jti="jti-dashboard",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            dashboard_binding_token=dashboard_binding_token,
        )
    )
