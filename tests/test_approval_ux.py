from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.dashboard import DashboardConfig, handle_dashboard_request
from craik.runtime.paths import ensure_craik_home
from craik.runtime.reviewing.approvals import (
    approval_queue_payload,
    decide_approval,
    open_approval_request,
)
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.tui import build_tui_snapshot, render_tui_snapshot
from craik.runtime.store import LocalStore

runner = CliRunner()
NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def test_approval_lifecycle_emits_decision_receipt(tmp_path: Path) -> None:
    home = tmp_path / "home"
    store = _seed_approval(home)

    try:
        payload = approval_queue_payload(store)
        result = decide_approval(
            store,
            "approval_shell",
            decision="denied",
            operator="operator:test",
            reason="target is too broad",
            decided_at=NOW,
        )
        reloaded = store.get_human_delegation("approval_shell")
        receipt = store.get_receipt(result.receipt.id)
    finally:
        store.close()

    assert payload["count"] == 1
    approval = payload["approvals"][0]
    assert approval["capability"] == "shell.execute"
    assert approval["target"] == "npm test"
    assert approval["risk"] == "runs a local command"
    assert approval["policy"] == "strict"
    assert approval["operator"] == "operator:test"
    assert approval["retry_path"] == "rerun the blocked command"
    assert reloaded is not None
    assert reloaded.status == "resolved"
    assert result.receipt.id in reloaded.receipt_ids
    assert receipt is not None
    assert receipt.result.status == "denied"
    assert receipt.operator_subject == "operator:test"
    assert receipt.result.metadata["retry_path"] == "rerun the blocked command"
    assert "Retry path: rerun the blocked command" in (reloaded.resolution or "")


def test_approval_cli_lists_shows_and_approves(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)
    store = _seed_approval(home)
    store.close()

    listed = runner.invoke(app, ["approvals", "list"], env=env)
    shown = runner.invoke(app, ["approvals", "show", "approval_shell"], env=env)
    approved = runner.invoke(
        app,
        ["approvals", "approve", "approval_shell", "--reason", "scope is bounded"],
        env=env,
    )

    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["approvals"][0]["id"] == "approval_shell"
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["retry_path"] == "rerun the blocked command"
    assert approved.exit_code == 0
    payload = json.loads(approved.stdout)
    assert payload["approval"]["status"] == "resolved"
    assert payload["receipt"]["result"]["status"] == "passed"
    assert payload["receipt"]["result"]["metadata"]["decision"] == "approved"


def test_approval_surfaces_queue_in_slash_dashboard_and_tui(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)
    store = _seed_approval(home)
    store.close()

    slash = dispatch_slash_command("/approvals", env=env)
    dashboard_api = handle_dashboard_request(
        "GET",
        "/api/approvals",
        {"X-Craik-Dashboard-Token": "dashboard-token"},
        b"",
        DashboardConfig(auth_token="dashboard-token"),
        env=env,
    )
    dashboard_page = handle_dashboard_request(
        "GET",
        "/approvals",
        {"X-Craik-Dashboard-Token": "dashboard-token"},
        b"",
        DashboardConfig(auth_token="dashboard-token"),
        env=env,
    )
    tui = render_tui_snapshot(build_tui_snapshot(env))

    assert json.loads(slash.text)["approvals"][0]["id"] == "approval_shell"
    assert dashboard_api.status == 200
    assert json.loads(dashboard_api.body)["count"] == 1
    assert b"open approvals: 1" in dashboard_page.body
    assert "Open: 1" in tui
    assert "/approvals" in tui


def _seed_approval(home: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    store.initialize()
    open_approval_request(
        store,
        approval_id="approval_shell",
        task_id="task_shell",
        capability="shell.execute",
        target="npm test",
        risk="runs a local command",
        policy="strict",
        requested_by="craik:runner",
        retry_path="rerun the blocked command",
        operator="operator:test",
        policy_envelope_id="strict",
        created_at=NOW,
    )
    return store


def _put_operator_session(home: Path) -> None:
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator:test",
            email="operator@example.invalid",
            display_name="Operator Test",
            groups=["maintainers"],
            issuer="https://issuer.example.invalid",
            id_token_jti="jti-approval",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
