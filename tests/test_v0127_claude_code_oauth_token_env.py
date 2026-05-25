from __future__ import annotations

import json
from datetime import UTC, datetime

from craik.runtime.auth.login import auth_status_rows
from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources.anthropic_env import (
    ANTHROPIC_API_KEY_ENV,
    CLAUDE_CODE_OAUTH_TOKEN_ENV,
    CRAIK_ANTHROPIC_API_KEY_ENV,
    resolve_anthropic_credential_from_env,
)
from craik.runtime.auth.sources.api_key import EnvVarApiKeySource
from craik.runtime.doctor import run_doctor
from craik.runtime.paths import ensure_craik_home


def test_resolves_claude_code_oauth_token(monkeypatch) -> None:
    monkeypatch.setenv(CLAUDE_CODE_OAUTH_TOKEN_ENV, "sk-ant-oat01-xxx")
    monkeypatch.delenv(ANTHROPIC_API_KEY_ENV, raising=False)

    credential = resolve_anthropic_credential_from_env()

    assert credential is not None
    assert credential.token == "sk-ant-oat01-xxx"
    assert credential.source == "env:CLAUDE_CODE_OAUTH_TOKEN"
    assert "Anthropic CLI" in credential.display


def test_claude_code_token_preferred_over_anthropic_api_key(monkeypatch) -> None:
    monkeypatch.setenv(CLAUDE_CODE_OAUTH_TOKEN_ENV, "sk-ant-oat01-claude")
    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, "sk-ant-api-key-direct")

    credential = resolve_anthropic_credential_from_env()

    assert credential is not None
    assert credential.token == "sk-ant-oat01-claude"
    assert credential.source == "env:CLAUDE_CODE_OAUTH_TOKEN"


def test_falls_back_to_anthropic_api_key(monkeypatch) -> None:
    monkeypatch.delenv(CLAUDE_CODE_OAUTH_TOKEN_ENV, raising=False)
    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, "sk-ant-api-key")

    credential = resolve_anthropic_credential_from_env()

    assert credential is not None
    assert credential.token == "sk-ant-api-key"
    assert credential.source == "env:ANTHROPIC_API_KEY"


def test_falls_back_to_craik_anthropic_api_key(monkeypatch) -> None:
    monkeypatch.delenv(CLAUDE_CODE_OAUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv(ANTHROPIC_API_KEY_ENV, raising=False)
    monkeypatch.setenv(CRAIK_ANTHROPIC_API_KEY_ENV, "sk-ant-craik-key")

    credential = resolve_anthropic_credential_from_env()

    assert credential is not None
    assert credential.token == "sk-ant-craik-key"
    assert credential.source == "env:CRAIK_ANTHROPIC_API_KEY"


def test_returns_none_when_neither_env_set(monkeypatch) -> None:
    monkeypatch.delenv(CLAUDE_CODE_OAUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv(ANTHROPIC_API_KEY_ENV, raising=False)
    monkeypatch.delenv(CRAIK_ANTHROPIC_API_KEY_ENV, raising=False)

    assert resolve_anthropic_credential_from_env() is None


def test_whitespace_only_token_treated_as_unset(monkeypatch) -> None:
    monkeypatch.setenv(CLAUDE_CODE_OAUTH_TOKEN_ENV, "   ")
    monkeypatch.delenv(ANTHROPIC_API_KEY_ENV, raising=False)
    monkeypatch.delenv(CRAIK_ANTHROPIC_API_KEY_ENV, raising=False)

    assert resolve_anthropic_credential_from_env() is None


def test_env_api_key_source_prefers_claude_code_oauth_token(monkeypatch) -> None:
    monkeypatch.setenv(CLAUDE_CODE_OAUTH_TOKEN_ENV, "sk-ant-oat01-claude")
    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, "sk-ant-api-key")

    headers = EnvVarApiKeySource(ANTHROPIC_API_KEY_ENV).headers_for("anthropic")
    status = EnvVarApiKeySource(ANTHROPIC_API_KEY_ENV).status()

    assert headers["x-api-key"] == "sk-ant-oat01-claude"
    assert headers["anthropic-version"] == "2023-06-01"
    assert status.status == "ok"
    assert status.detail == "Anthropic CLI OAuth token (env)"


def test_auth_status_surfaces_anthropic_credential_source() -> None:
    row = auth_status_rows(
        [_anthropic_env_profile()],
        env={
            CLAUDE_CODE_OAUTH_TOKEN_ENV: "sk-ant-oat01-claude",
            ANTHROPIC_API_KEY_ENV: "sk-ant-api-key",
        },
    )[0].as_dict()

    assert row["health_status"] == "ok"
    assert row["credential_source"] == "Anthropic CLI OAuth token (env)"
    assert "sk-ant" not in json.dumps(row)


def test_doctor_surfaces_claude_code_oauth_token(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})

    payload = run_doctor(
        paths,
        env={CLAUDE_CODE_OAUTH_TOKEN_ENV: "sk-ant-oat01-claude"},
    )

    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["anthropic_env_credential"]["status"] == "pass"
    assert "Anthropic CLI OAuth token" in checks["anthropic_env_credential"]["summary"]
    assert "sk-ant" not in json.dumps(checks["anthropic_env_credential"])


def _anthropic_env_profile() -> AuthProfile:
    return AuthProfile(
        id="anthropic:env",
        kind=CredentialKind.API_KEY,
        provider_family="anthropic",
        metadata={"env_var": ANTHROPIC_API_KEY_ENV},
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
    )
