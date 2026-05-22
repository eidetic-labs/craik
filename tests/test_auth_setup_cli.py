from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth import AuthProfileStore
from craik.runtime.auth.pool import CredentialPool

runner = CliRunner()


def test_auth_setup_openai_writes_profile_and_pool(tmp_path: Path) -> None:
    home = tmp_path / "home"
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


def test_auth_setup_supports_anthropic_gemini_and_local_dry_run(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    anthropic = runner.invoke(app, ["auth", "setup", "anthropic", "--dry-run"], env=env)
    gemini = runner.invoke(app, ["auth", "setup", "gemini", "--dry-run"], env=env)
    local = runner.invoke(app, ["auth", "setup", "local", "--dry-run"], env=env)

    assert anthropic.exit_code == 0, anthropic.output
    assert gemini.exit_code == 0, gemini.output
    assert local.exit_code == 0, local.output
    assert json.loads(anthropic.stdout)["profile"]["id"] == "anthropic:default"
    assert json.loads(gemini.stdout)["profile"]["provider_family"] == "gemini"
    local_payload = json.loads(local.stdout)
    assert local_payload["profile"]["provider_family"] == "chat_completions"
    assert local_payload["profile"]["metadata"]["allow_local_base_url"] is True
    assert "Confirm the local OpenAI-compatible server" in local_payload["guidance"][1]
    assert not AuthProfileStore(tmp_path / "home").list()


def test_auth_setup_secret_ref_output_is_redacted(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

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
    env = {"CRAIK_HOME": str(tmp_path / "home")}

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
