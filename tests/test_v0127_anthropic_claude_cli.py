from __future__ import annotations

import pytest

from craik.runtime.auth.profile import CredentialKind
from craik.runtime.auth.sources.anthropic_claude_cli import (
    AnthropicClaudeCliError,
    claude_cli_runtime_status,
    create_claude_cli_profile,
    export_claude_code_oauth_token,
    extract_claude_code_oauth_token,
    store_claude_cli_token_profile,
)
from craik.runtime.auth.sources.anthropic_env import anthropic_headers_for_credential
from craik.runtime.auth.sources.factory import source_for_auth_profile
from craik.runtime.shell.credential_storage import CredentialStorageStatus


def test_extract_claude_code_oauth_token_from_export_text() -> None:
    assert (
        extract_claude_code_oauth_token(
            "export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-example_token"
        )
        == "sk-ant-oat01-example_token"
    )


def test_extract_claude_code_oauth_token_handles_wrapped_output() -> None:
    assert (
        extract_claude_code_oauth_token("CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-\nwrapped")
        == "sk-ant-oat01-wrapped"
    )


def test_extract_claude_code_oauth_token_preserves_hash_character() -> None:
    assert (
        extract_claude_code_oauth_token(
            "export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-prefix#suffix"
        )
        == "sk-ant-oat01-prefix#suffix"
    )


def test_export_claude_code_oauth_token_runs_setup_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.shutil.which",
        lambda _: "/bin/claude",
    )

    def _runner(*args, **kwargs):
        assert args[0] == ("/bin/claude", "setup-token")
        return 0, "export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-from-cli\n", ""

    assert export_claude_code_oauth_token(runner=_runner) == "sk-ant-oat01-from-cli"


def test_export_claude_code_oauth_token_redacts_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.shutil.which",
        lambda _: "/bin/claude",
    )

    def _runner(*args, **kwargs):
        return 1, "", "failed with sk-ant-oat01-secret-token"

    with pytest.raises(AnthropicClaudeCliError) as exc_info:
        export_claude_code_oauth_token(runner=_runner)

    assert "sk-ant-oat01-secret-token" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_claude_cli_runtime_status_reports_logged_in(monkeypatch) -> None:
    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.shutil.which",
        lambda _: "/bin/claude",
    )

    def _runner(*args, **kwargs):
        assert args[0] == ("/bin/claude", "auth", "status")
        return 0, '{"loggedIn": true, "authMethod": "oauth"}', ""

    assert claude_cli_runtime_status(runner=_runner).status == "ok"


def test_claude_cli_runtime_status_rejects_logged_out(monkeypatch) -> None:
    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.shutil.which",
        lambda _: "/bin/claude",
    )

    def _runner(*args, **kwargs):
        return 1, '{"loggedIn": false, "authMethod": "none"}', ""

    status = claude_cli_runtime_status(runner=_runner)

    assert status.status == "rejected"
    assert "loggedIn" in str(status.detail)


def test_store_claude_cli_token_profile_writes_keyring(monkeypatch) -> None:
    stored: dict[str, str] = {}

    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.put_cached_credential",
        lambda ref, value, *, env=None: (
            stored.__setitem__(ref, value)
            or CredentialStorageStatus(backend="test-keyring", status="available", secure=True)
        ),
    )

    result = store_claude_cli_token_profile("sk-ant-oat01-token")

    assert result.profile.kind is CredentialKind.KEYRING_REF
    assert result.profile.metadata["credential_mode"] == "oauth"
    assert result.profile.metadata["source"] == "claude-cli-setup-token"
    assert stored == {"anthropic:default:claude-cli-token": "sk-ant-oat01-token"}


def test_create_claude_cli_profile_uses_external_cli_marker(monkeypatch) -> None:
    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    result = create_claude_cli_profile()

    assert result.profile.kind is CredentialKind.MARKER
    assert result.profile.metadata["source"] == "claude-cli-external"
    assert result.profile.metadata["external_runtime"] == "claude-cli"
    assert result.profile.metadata["credential_backend"] == "claude-cli"
    assert result.profile.metadata["credential_mode"] == "oauth"
    assert result.credential_storage_backend == "claude-cli"


def test_claude_cli_profile_uses_bearer_headers(monkeypatch) -> None:
    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.put_cached_credential",
        lambda ref, value, *, env=None: CredentialStorageStatus(
            backend="test-keyring",
            status="available",
            secure=True,
        ),
    )
    result = store_claude_cli_token_profile("sk-ant-oat01-token", env={"CRAIK_HOME": "test"})
    monkeypatch.setattr(
        "craik.runtime.auth.sources.keyring_ref.get_cached_credential",
        lambda ref: type("Credential", (), {"value": "sk-ant-oat01-token"})(),
    )

    headers = source_for_auth_profile(result.profile).headers_for("anthropic")

    assert headers["Authorization"] == "Bearer sk-ant-oat01-token"
    assert headers["anthropic-beta"] == "claude-code-20250219,oauth-2025-04-20"
    assert headers["user-agent"].startswith("claude-cli/")
    assert "x-api-key" not in headers


def test_anthropic_api_key_still_uses_x_api_key() -> None:
    headers = anthropic_headers_for_credential("sk-ant-api03-token")

    assert headers["x-api-key"] == "sk-ant-api03-token"
    assert "Authorization" not in headers
