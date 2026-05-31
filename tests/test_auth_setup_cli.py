from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth import AuthProfileStore
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.auth.pool import CredentialPool

runner = CliRunner()


def test_auth_setup_openai_writes_profile_and_pool(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_session(home)
    env = {"CRAIK_HOME": str(home), "CRAIK_OPENAI_API_KEY": "craik-test-not-a-real-key"}

    result = runner.invoke(app, ["auth", "setup", "openai"], env=env)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["redacted"] is True
    assert payload["status"]["status"] == "ok"
    assert payload["profile"]["id"] == "openai:default"
    assert payload["profile"]["metadata"]["env_var"] == "CRAIK_OPENAI_API_KEY"
    assert "craik-test-not-a-real-key" not in result.stdout
    assert AuthProfileStore(home).get("openai:default").provider_family == "openai"
    assert CredentialPool(home).get("openai:default").profiles[0].profile_id == "openai:default"


def test_auth_add_and_remove_emit_single_json_payload(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_session(home)
    env = {"CRAIK_HOME": str(home)}

    added = runner.invoke(
        app,
        [
            "auth",
            "add",
            "openai:test",
            "--kind",
            "api-key",
            "--env-var",
            "CRAIK_TEST_OPENAI_KEY",
        ],
        env=env,
    )

    assert added.exit_code == 0, added.output
    added_payload = json.loads(added.stdout)
    assert added_payload["id"] == "openai:test"
    assert added_payload["metadata"]["env_var"] == "CRAIK_TEST_OPENAI_KEY"
    assert AuthProfileStore(home).get("openai:test").provider_family == "openai"

    removed = runner.invoke(app, ["auth", "remove", "openai:test"], env=env)

    assert removed.exit_code == 0, removed.output
    assert json.loads(removed.stdout) == {"removed": "openai:test"}


def test_operator_whoami_and_logout_emit_structured_payloads(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_session(home)
    env = {"CRAIK_HOME": str(home)}

    whoami = runner.invoke(app, ["whoami"], env=env)
    logout = runner.invoke(app, ["logout"], env=env)

    assert whoami.exit_code == 0, whoami.output
    whoami_payload = json.loads(whoami.stdout)
    assert whoami_payload["subject"] == "operator-123"
    assert whoami_payload["email"] == "operator@example.test"
    assert logout.exit_code == 0, logout.output
    assert json.loads(logout.stdout) == {"logged_out": True, "revoked": False}


def test_auth_setup_supports_anthropic_gemini_and_local_dry_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_session(home)
    env = {"CRAIK_HOME": str(home)}

    anthropic = runner.invoke(app, ["auth", "setup", "anthropic", "--dry-run"], env=env)
    gemini = runner.invoke(app, ["auth", "setup", "gemini", "--dry-run"], env=env)
    local = runner.invoke(app, ["auth", "setup", "local", "--dry-run"], env=env)

    assert anthropic.exit_code == 0, anthropic.output
    assert gemini.exit_code == 0, gemini.output
    assert local.exit_code == 0, local.output
    assert json.loads(anthropic.stdout)["profile"]["id"] == "anthropic:default"
    assert json.loads(gemini.stdout)["profile"]["provider_family"] == "google"
    local_payload = json.loads(local.stdout)
    assert local_payload["profile"]["provider_family"] == "chat_completions"
    assert local_payload["profile"]["metadata"]["allow_local_base_url"] is True
    assert any(
        "WARNING: Local model endpoint uses plaintext HTTP" in item
        for item in local_payload["guidance"]
    )
    assert any(
        "Confirm the local OpenAI-compatible server" in item
        for item in local_payload["guidance"]
    )
    assert not AuthProfileStore(tmp_path / "home").list()


def test_auth_setup_secret_ref_output_is_redacted(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_session(home)
    env = {"CRAIK_HOME": str(home)}

    result = runner.invoke(
        app,
        [
            "auth",
            "setup",
            "openai",
            "--secret-ref",
            "OPENAI_API_KEY",
            "--dry-run",
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["profile"]["kind"] == "secret-ref"
    assert payload["status"]["status"] == "rejected"
    assert "Verify the configured secret reference resolves before live use." in payload["guidance"]
    assert "craik-test-not-a-real-key" not in result.stdout


def test_auth_setup_rejects_unsafe_local_base_url_and_missing_file_secret_root(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    _put_session(home)
    env = {"CRAIK_HOME": str(home)}

    unsafe = runner.invoke(
        app,
        ["auth", "setup", "openai", "--base-url", "http://127.0.0.1:11434/v1"],
        env=env,
    )
    missing_root = runner.invoke(
        app,
        [
            "auth",
            "setup",
            "openai",
            "--secret-ref",
            "openai/api-key",
            "--secret-manager",
            "file",
        ],
        env=env,
    )

    assert unsafe.exit_code == 2
    assert "HTTPS" in unsafe.output
    assert missing_root.exit_code == 2
    assert "secrets" in missing_root.output
    assert "required" in missing_root.output


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
