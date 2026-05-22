from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import CONTRACT_KINDS, LocalStore

runner = CliRunner()


def test_agent_lifecycle_cli_launch_status_stop_restart(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_session(home)

    launched = runner.invoke(
        app,
        [
            "agent",
            "launch",
            "--session-id",
            "agent_docs",
            "--project-id",
            "project_docs",
            "--provider-id",
            "provider_openai",
            "--model-id",
            "gpt-5.2",
            "--auth-profile-id",
            "openai:work",
        ],
        env=env,
    )
    status = runner.invoke(app, ["agent", "status", "agent_docs"], env=env)
    stopped = runner.invoke(
        app,
        ["agent", "stop", "agent_docs", "--reason", "operator stop"],
        env=env,
    )
    restarted = runner.invoke(
        app,
        ["agent", "restart", "agent_docs", "--reason", "operator restart"],
        env=env,
    )

    assert launched.exit_code == 0, launched.output
    assert status.exit_code == 0, status.output
    assert stopped.exit_code == 0, stopped.output
    assert restarted.exit_code == 0, restarted.output
    launch_payload = json.loads(launched.stdout)
    status_payload = json.loads(status.stdout)
    stopped_payload = json.loads(stopped.stdout)
    restarted_payload = json.loads(restarted.stdout)
    assert launch_payload["launched"] is True
    assert launch_payload["boundary"]["one_shot_run"].endswith(" run execute")
    assert status_payload["hmac_status"] == "verified"
    assert status_payload["session"]["id"] == "agent_docs"
    assert status_payload["session"]["operator_subject"] == "operator-123"
    assert stopped_payload["session"]["status"] == "stopped"
    assert stopped_payload["session"]["pid"] is None
    assert restarted_payload["session"]["status"] == "running"
    assert restarted_payload["session"]["stopped_at"] is None


def test_agent_cli_rejects_invalid_lifecycle_transitions(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_session(home)
    first = runner.invoke(
        app,
        ["agent", "launch", "--session-id", "agent_docs"],
        env=env,
    )
    duplicate = runner.invoke(
        app,
        ["agent", "launch", "--session-id", "agent_docs"],
        env=env,
    )
    invalid_restart = runner.invoke(app, ["agent", "restart", "agent_docs"], env=env)

    assert first.exit_code == 0, first.output
    assert duplicate.exit_code == 2
    assert "agent session already exists" in duplicate.output
    assert invalid_restart.exit_code == 2
    assert "active sessions cannot" in invalid_restart.output
    assert "be restarted" in invalid_restart.output


def test_agent_cli_requires_active_operator_session(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    result = runner.invoke(app, ["agent", "launch", "--session-id", "agent_docs"], env=env)

    assert result.exit_code == 2
    assert "active operator session required; run craik auth login" in result.output


def test_agent_status_surfaces_tampered_session_hmac(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_session(home)
    launched = runner.invoke(
        app,
        ["agent", "launch", "--session-id", "agent_docs"],
        env=env,
    )
    assert launched.exit_code == 0, launched.output
    _tamper_agent_session(home, "agent_docs")

    status = runner.invoke(app, ["agent", "status", "agent_docs"], env=env)

    assert status.exit_code == 0, status.output
    payload = json.loads(status.stdout)
    assert payload["hmac_status"] == "tampered"
    assert payload["session"]["provider_id"] == "provider_tampered"


def test_agent_cli_prompt_runs_provider_backed_session(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_session(home)
    project_id = _seed_project(home, tmp_path)
    launched = runner.invoke(
        app,
        [
            "agent",
            "launch",
            "--session-id",
            "agent_docs",
            "--project-id",
            project_id,
            "--provider-id",
            "provider_openai",
        ],
        env=env,
    )
    prompted = runner.invoke(
        app,
        ["agent", "prompt", "agent_docs", "Implement a provider-backed agent prompt."],
        env=env,
    )

    assert launched.exit_code == 0, launched.output
    assert prompted.exit_code == 0, prompted.output
    payload = json.loads(prompted.stdout)
    assert payload["schema"] == "craik.agent_prompt_execution"
    assert payload["exit_behavior"] == "completed"
    assert payload["session"]["status"] == "idle"
    assert payload["run"]["status"] == "completed"
    assert [event["event_type"] for event in payload["events"]] == [
        "prompt_received",
        "run_completed",
    ]


def test_agent_cli_recover_marks_failure_and_resume(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_session(home)
    launched = runner.invoke(
        app,
        ["agent", "launch", "--session-id", "agent_docs"],
        env=env,
    )
    recovered = runner.invoke(
        app,
        [
            "agent",
            "recover",
            "agent_docs",
            "--reason",
            "auth_expired",
            "--detail",
            "provider token=secret-token expired",
        ],
        env=env,
    )
    resumed = runner.invoke(
        app,
        ["agent", "recover", "agent_docs", "--action", "resume"],
        env=env,
    )

    assert launched.exit_code == 0, launched.output
    assert recovered.exit_code == 0, recovered.output
    assert resumed.exit_code == 0, resumed.output
    recovery_payload = json.loads(recovered.stdout)
    resume_payload = json.loads(resumed.stdout)
    assert recovery_payload["session"]["status"] == "auth_expired"
    assert recovery_payload["session"]["recovery_metadata"]["recovery_reason"] == "auth_expired"
    assert recovery_payload["session"]["recovery_metadata"]["recovery_detail"] == (
        "provider token=[REDACTED] expired"
    )
    assert "secret-token" not in recovered.stdout
    assert resume_payload["session"]["status"] == "idle"
    assert resume_payload["session"]["recovery_metadata"]["recovery_action"] == "resume"


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


def _seed_project(home: Path, tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        return ProjectRegistry(store).add_project(repo, name="Example").id
    finally:
        store.close()


def _tamper_agent_session(home: Path, session_id: str) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        kind = CONTRACT_KINDS["craik.agent_session_state"]
        row = store._connection.execute(
            "SELECT payload_json FROM records WHERE kind = ? AND id = ?",
            (kind, session_id),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row["payload_json"]))
        payload["provider_id"] = "provider_tampered"
        store._connection.execute(
            "UPDATE records SET payload_json = ? WHERE kind = ? AND id = ?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), kind, session_id),
        )
        store._connection.commit()
    finally:
        store.close()


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_NAME": "Craik Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Craik Test",
        },
    )
