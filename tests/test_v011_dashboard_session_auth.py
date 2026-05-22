from __future__ import annotations

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
        {"X-Craik-Operator-Session": "jti-dashboard"},
        b"",
        config,
        env=env,
    )

    assert missing.status == 401
    assert wrong.status == 401
    assert accepted.status == 200
    assert json.loads(accepted.body)["readiness"]["operator_authenticated"] is True


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


def _put_operator_session(home: Path) -> None:
    OperatorSessionStore(home).put(
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
