import json
from pathlib import Path

from craik.runtime.dashboard import DashboardConfig, handle_dashboard_request


def test_dashboard_action_rejects_foreign_origin_post(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    config = DashboardConfig(auth_token="dashboard-token")

    response = handle_dashboard_request(
        "POST",
        "/api/actions",
        {
            "Authorization": "Bearer dashboard-token",
            "Origin": "https://attacker.example",
        },
        json.dumps({"command": "/help status"}).encode("utf-8"),
        config,
        env=env,
    )

    assert response.status == 403
    assert json.loads(response.body)["error"] == "dashboard origin not allowed"


def test_dashboard_action_allows_same_origin_read_only_command(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    config = DashboardConfig(auth_token="dashboard-token")

    response = handle_dashboard_request(
        "POST",
        "/api/actions",
        {
            "Authorization": "Bearer dashboard-token",
            "Origin": "http://127.0.0.1:8787",
        },
        json.dumps({"command": "/help status"}).encode("utf-8"),
        config,
        env=env,
    )
    payload = json.loads(response.body)

    assert response.status == 200
    assert payload["command"] == "/help status"
    assert "Usage: /status" in payload["text"]


def test_dashboard_action_rejects_mutating_command_without_origin(
    tmp_path: Path,
) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    config = DashboardConfig(auth_token="dashboard-token")

    response = handle_dashboard_request(
        "POST",
        "/api/actions",
        {"Authorization": "Bearer dashboard-token"},
        json.dumps({"command": "/auth login"}).encode("utf-8"),
        config,
        env=env,
    )

    assert response.status == 403
    assert json.loads(response.body)["error"] == (
        "mutating slash commands are not allowed from the dashboard"
    )
