from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth import oauth_provider_login
from craik.runtime.auth.login import AuthCaptureResult, auth_status_rows
from craik.runtime.auth.oauth_provider_login import OAuthLoginResult, browser_oauth_login
from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources import (
    ProviderOAuthCredentialSource,
    provider_oauth,
    source_for_auth_profile,
)
from craik.runtime.auth.sources.anthropic_oauth import AnthropicOAuthError
from craik.runtime.auth.sources.openai_oauth import (
    OPENAI_OAUTH_CLIENT_ID,
    OPENAI_OAUTH_REDIRECT_URI,
    OpenAIOAuthError,
    OpenAIOAuthTokenSet,
)
from craik.runtime.shell.credential_storage import CredentialStorageStatus, StoredCredential

runner = CliRunner()


def test_source_for_auth_profile_maps_provider_oauth_profiles() -> None:
    source = source_for_auth_profile(_oauth_profile())

    assert isinstance(source, ProviderOAuthCredentialSource)


def test_provider_oauth_source_returns_bearer_header_without_secret_specific_headers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        provider_oauth,
        "get_cached_credential",
        lambda ref: StoredCredential(value=f"value-for-{ref}", backend="test", secure=True),
    )

    headers = ProviderOAuthCredentialSource(_oauth_profile()).headers_for("openai")

    assert headers == {"Authorization": "Bearer value-for-openai:subscription:access"}
    assert "x-api-key" not in headers
    assert "x-goog-api-key" not in headers


def test_provider_oauth_source_uses_anthropic_api_key_header(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_oauth,
        "get_cached_credential",
        lambda ref: StoredCredential(value=f"value-for-{ref}", backend="test", secure=True),
    )

    headers = ProviderOAuthCredentialSource(_oauth_profile(provider="anthropic")).headers_for(
        "anthropic"
    )

    assert headers == {"x-api-key": "value-for-anthropic:subscription:access"}
    assert "Authorization" not in headers


def test_provider_oauth_source_refreshes_expired_access_token(monkeypatch) -> None:
    stored = {
        "openai:subscription:access": "expired-access",
        "openai:subscription:refresh": "stored-refresh",
    }
    writes: dict[str, str] = {}

    def _get(ref: str) -> StoredCredential:
        return StoredCredential(value=stored[ref], backend="test", secure=True)

    class _Client:
        def refresh_access_token(self, *, refresh_token: str):
            assert refresh_token == "stored-refresh"
            return (
                OpenAIOAuthTokenSet(
                    access_token="fresh-access",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                    scope=["model.request"],
                ),
                "fresh-refresh",
            )

    monkeypatch.setattr(provider_oauth, "get_cached_credential", _get)
    monkeypatch.setattr(
        provider_oauth,
        "put_cached_credential",
        lambda ref, value: writes.__setitem__(ref, value),
    )
    monkeypatch.setattr(
        provider_oauth.ProviderOAuthCredentialSource,
        "_client",
        lambda self: _Client(),
    )

    headers = ProviderOAuthCredentialSource(
        _oauth_profile(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    ).headers_for("openai")

    assert headers == {"Authorization": "Bearer fresh-access"}
    assert writes == {
        "openai:subscription:access": "fresh-access",
        "openai:subscription:refresh": "fresh-refresh",
    }


def test_auth_status_rows_include_oauth_expiration(monkeypatch) -> None:
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    monkeypatch.setattr(
        provider_oauth,
        "get_cached_credential",
        lambda ref: StoredCredential(value="token", backend="test", secure=True),
    )

    row = auth_status_rows([_oauth_profile(expires_at=expires_at)])[0].as_dict()

    assert row["kind"] == "oauth"
    assert row["health_status"] == "ok"
    assert row["oauth_expires_at"] == expires_at.isoformat()
    assert row["billing_surface"] == "OpenAI subscription"
    assert row["redacted"] is True


def test_auth_status_rows_include_provider_billing_surfaces(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api")
    rows = [
        row.as_dict()
        for row in auth_status_rows(
            [
                AuthProfile(
                    id="anthropic:env",
                    kind=CredentialKind.API_KEY,
                    provider_family="anthropic",
                    metadata={"env_var": "ANTHROPIC_API_KEY"},
                    created_at=datetime.now(UTC),
                ),
                _oauth_profile(provider="openai"),
                AuthProfile(
                    id="gemini:vertex",
                    kind=CredentialKind.OAUTH,
                    provider_family="gemini",
                    metadata={"credential_source": "adc", "gcp_project_id": "craik-project"},
                    created_at=datetime.now(UTC),
                    oauth_authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
                    oauth_token_endpoint="https://oauth2.googleapis.com/token",
                    oauth_client_id="google-adc",
                    oauth_scope_list=["https://www.googleapis.com/auth/cloud-platform"],
                ),
                AuthProfile(
                    id="anthropic:claude-cli",
                    kind=CredentialKind.MARKER,
                    provider_family="anthropic",
                    metadata={
                        "credential_mode": "claude-cli",
                        "external_runtime": "claude-cli",
                    },
                    created_at=datetime.now(UTC),
                ),
            ],
            env={"ANTHROPIC_API_KEY": "sk-ant-api"},
            validate=False,
        )
    ]

    billing_by_id = {row["id"]: row["billing_surface"] for row in rows}
    assert billing_by_id == {
        "anthropic:env": "Anthropic Console API (per-token)",
        "anthropic:claude-cli": "Claude CLI subscription",
        "openai:subscription": "OpenAI subscription",
        "gemini:vertex": "GCP project (Vertex AI)",
    }


def test_auth_login_oauth_mode_uses_browser_oauth_flow(monkeypatch, tmp_path) -> None:
    profile = _oauth_profile()

    def _login(provider: str, **kwargs):
        assert provider == "openai"
        assert kwargs["profile_id"] is None
        assert kwargs["project_id"] is None
        assert kwargs["browser_opener"]("https://auth.example.test/authorize") is False
        return OAuthLoginResult(
            capture=AuthCaptureResult(
                provider="openai",
                profile=profile,
                status=profile_runtime_ok(),
                credential_storage=CredentialStorageStatus(
                    backend="test-keyring",
                    status="available",
                    secure=True,
                ),
            ),
            authorization_url="https://auth.example.test/authorize",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _login)
    result = runner.invoke(
        app,
        ["auth", "login", "openai", "--mode=oauth", "--no-browser", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout[result.stdout.index("{") :])
    assert payload["kind"] == "oauth"
    assert payload["browser_opened"] is False
    assert payload["authorization_url"] == "https://auth.example.test/authorize"
    assert "access-token" not in result.output


def test_auth_login_anthropic_defaults_to_claude_cli(monkeypatch, tmp_path) -> None:
    profile = AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "oauth"},
        created_at=datetime.now(UTC),
    )

    def _login(**kwargs):
        assert kwargs["profile_id"] is None
        return OAuthLoginResult(
            capture=AuthCaptureResult(
                provider="anthropic",
                profile=profile,
                status=profile_runtime_ok(),
                credential_storage=CredentialStorageStatus(
                    backend="test-keyring",
                    status="available",
                    secure=True,
                ),
            ),
            authorization_url="claude",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.anthropic_claude_cli_login", _login)
    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["provider"] == "anthropic"
    assert payload["kind"] == "marker"
    assert payload["mode"] == "oauth"
    assert payload["auth_transport"] == "claude-cli"
    assert payload["authorization_url"] == "claude"


def test_auth_login_anthropic_oauth_mode_uses_cli_marker(monkeypatch, tmp_path) -> None:
    profile = AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "oauth"},
        created_at=datetime.now(UTC),
    )

    def _login(**kwargs):
        return OAuthLoginResult(
            capture=AuthCaptureResult(
                provider="anthropic",
                profile=profile,
                status=profile_runtime_ok(),
                credential_storage=CredentialStorageStatus(
                    backend="claude-cli",
                    status="available",
                    secure=True,
                ),
            ),
            authorization_url="claude auth login",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.anthropic_claude_cli_login", _login)
    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--mode=oauth", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["kind"] == "marker"
    assert payload["mode"] == "oauth"
    assert payload["auth_transport"] == "claude-cli"


def test_auth_login_gemini_defaults_to_oauth_mode(monkeypatch, tmp_path) -> None:
    profile = _oauth_profile(provider="gemini")

    def _login(**kwargs):
        assert kwargs["profile_id"] is None
        assert kwargs["project_id"] is None
        assert kwargs["service_account_path"] is None
        return OAuthLoginResult(
            capture=AuthCaptureResult(
                provider="gemini",
                profile=profile,
                status=profile_runtime_ok(),
                credential_storage=CredentialStorageStatus(
                    backend="google-auth",
                    status="available",
                    secure=True,
                ),
            ),
            authorization_url="gcloud auth application-default login",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.google_oauth_login", _login)
    result = runner.invoke(
        app,
        ["auth", "login", "gemini", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["provider"] == "gemini"
    assert payload["authorization_url"] == "gcloud auth application-default login"


def test_auth_login_openai_defaults_to_oauth_without_openai_api_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    profile = _oauth_profile()

    def _login(provider: str, **kwargs):
        assert provider == "openai"
        assert kwargs["browser_opener"]("https://auth.example.test/authorize") is False
        return OAuthLoginResult(
            capture=AuthCaptureResult(
                provider="openai",
                profile=profile,
                status=profile_runtime_ok(),
                credential_storage=CredentialStorageStatus(
                    backend="test-keyring",
                    status="available",
                    secure=True,
                ),
            ),
            authorization_url="https://auth.example.test/authorize",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _login)
    monkeypatch.setattr("craik.cli_auth_login.webbrowser.open", lambda url: False)
    result = runner.invoke(
        app,
        ["auth", "login", "openai", "--json"],
        input="\n",
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout[result.stdout.index("{") :])
    assert payload["provider"] == "openai"
    assert payload["kind"] == "oauth"
    assert payload["authorization_url"] == "https://auth.example.test/authorize"


def test_auth_login_openai_defaults_to_api_key_when_openai_api_key_is_set(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    calls: dict[str, str] = {}
    profile = AuthProfile(
        id="openai:default",
        kind=CredentialKind.KEYRING_REF,
        provider_family="openai",
        metadata={"ref": "openai:default:api-key"},
        created_at=datetime.now(UTC),
    )

    def _capture(provider: str, **kwargs):
        calls["provider"] = provider
        calls["credential"] = kwargs["credential"]
        return AuthCaptureResult(
            provider=provider,
            profile=profile,
            status=profile_runtime_ok(),
            credential_storage=CredentialStorageStatus(
                backend="test-keyring",
                status="available",
                secure=True,
            ),
        )

    def _oauth(provider: str, **kwargs):
        raise AssertionError("openai should default to api-key mode")

    monkeypatch.setattr("craik.cli_auth_login.capture_and_cache_login", _capture)
    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _oauth)
    result = runner.invoke(
        app,
        ["auth", "login", "openai", "--no-browser", "--json"],
        input="sk-test\n",
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout[result.stdout.index("{") :])
    assert payload["provider"] == "openai"
    assert payload["kind"] == "keyring-ref"
    assert calls == {"provider": "openai", "credential": "sk-test"}


def test_auth_login_openai_oauth_disclosure_precedes_browser_open(monkeypatch, tmp_path) -> None:
    profile = _oauth_profile()

    def _login(provider: str, **kwargs):
        assert provider == "openai"
        assert kwargs["browser_opener"]("https://auth.example.test/authorize") is True
        return OAuthLoginResult(
            capture=AuthCaptureResult(
                provider="openai",
                profile=profile,
                status=profile_runtime_ok(),
                credential_storage=CredentialStorageStatus(
                    backend="test-keyring",
                    status="available",
                    secure=True,
                ),
            ),
            authorization_url="https://auth.example.test/authorize",
            browser_opened=True,
        )

    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _login)
    monkeypatch.setattr("craik.cli_auth_login.webbrowser.open", lambda url: True)

    result = runner.invoke(
        app,
        ["auth", "login", "openai", "--mode=oauth", "--json"],
        input="\n",
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert 'consent page will identify the requesting application as "Codex"' in result.output
    assert "--mode=api-key" in result.output


def test_browser_oauth_login_openai_uses_codex_client_and_fixed_redirect(
    monkeypatch,
    tmp_path,
) -> None:
    seen: dict[str, object] = {}

    class _Listener:
        def __init__(self, **kwargs):
            seen["listener_kwargs"] = kwargs
            self.redirect_uri = OPENAI_OAUTH_REDIRECT_URI

        def start(self):
            return self

        def wait(self):
            return SimpleNamespace(code="auth-code")

        def close(self):
            seen["closed"] = True

    def _exchange(self, **kwargs):
        seen["exchange"] = kwargs
        return (
            OpenAIOAuthTokenSet(
                access_token="access-token",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                scope=["openid"],
            ),
            "refresh-token",
        )

    def _store(token_set, refresh_token, **kwargs):
        seen["store"] = kwargs
        return _oauth_profile(provider="openai")

    opened: list[str] = []
    monkeypatch.setattr(oauth_provider_login, "OAuthLoopbackListener", _Listener)
    monkeypatch.setattr(oauth_provider_login.OpenAIOAuthClient, "exchange_code", _exchange)
    monkeypatch.setattr(oauth_provider_login, "store_openai_oauth_profile", _store)

    result = browser_oauth_login(
        "openai",
        browser_opener=lambda url: opened.append(url) or True,
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    params = parse_qs(urlparse(opened[0]).query)
    assert params["client_id"] == ["app_EMoamEEZ73f0CkXaXp7hrann"]
    assert params["redirect_uri"] == [OPENAI_OAUTH_REDIRECT_URI]
    assert params["code_challenge_method"] == ["S256"]
    assert seen["listener_kwargs"]["port"] == 1455
    assert seen["listener_kwargs"]["callback_path"] == "/auth/callback"
    assert seen["exchange"]["redirect_uri"] == OPENAI_OAUTH_REDIRECT_URI
    assert result.capture.profile.kind is CredentialKind.OAUTH


def test_browser_oauth_login_openai_reports_port_1455_conflict(monkeypatch) -> None:
    class _Listener:
        def __init__(self, **kwargs):
            raise OSError("address already in use")

    monkeypatch.setattr(oauth_provider_login, "OAuthLoopbackListener", _Listener)

    with pytest.raises(OpenAIOAuthError, match="port 1455 is in use"):
        browser_oauth_login(
            "openai",
            browser_opener=lambda url: False,
        )


def test_browser_oauth_login_anthropic_is_not_supported() -> None:
    with pytest.raises(AnthropicOAuthError, match="not supported"):
        browser_oauth_login(
            "anthropic",
            browser_opener=lambda url: False,
            code_prompt=lambda prompt: "one-time-code",
        )


def test_anthropic_claude_cli_login_stores_external_cli_marker(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    result = oauth_provider_login.anthropic_claude_cli_login(
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.capture.profile.kind is CredentialKind.MARKER
    assert result.capture.profile.id == "anthropic:default"
    assert result.capture.profile.metadata["source"] == "claude-cli-external"
    assert result.capture.profile.metadata["external_runtime"] == "claude-cli"
    assert result.capture.profile.metadata["credential_mode"] == "oauth"
    assert result.capture.profile.metadata["billing_surface"] == "anthropic-claude-cli"
    assert result.capture.credential_storage.backend == "claude-cli"
    assert result.authorization_url == "claude auth login"


def test_auth_login_gemini_oauth_uses_adc_or_service_account_flow(monkeypatch, tmp_path) -> None:
    profile = _oauth_profile(provider="gemini")
    service_account = tmp_path / "service-account.json"
    service_account.write_text("{}", encoding="utf-8")

    def _login(**kwargs):
        assert kwargs["profile_id"] is None
        assert kwargs["project_id"] == "craik-project"
        assert kwargs["service_account_path"] == service_account
        return OAuthLoginResult(
            capture=AuthCaptureResult(
                provider="gemini",
                profile=profile,
                status=profile_runtime_ok(),
                credential_storage=CredentialStorageStatus(
                    backend="google-auth",
                    status="available",
                    secure=True,
                ),
            ),
            authorization_url="gcloud auth application-default login",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.google_oauth_login", _login)
    result = runner.invoke(
        app,
        [
            "auth",
            "login",
            "gemini",
            "--mode=oauth",
            "--project-id",
            "craik-project",
            "--service-account",
            str(service_account),
            "--json",
        ],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["provider"] == "gemini"
    assert payload["authorization_url"] == "gcloud auth application-default login"


def profile_runtime_ok():
    from craik.runtime.auth.profile import CredentialStatus

    return CredentialStatus(status="ok")


def _oauth_profile(expires_at: datetime | None = None, *, provider: str = "openai") -> AuthProfile:
    resolved_expires_at = expires_at or datetime.now(UTC) + timedelta(hours=1)
    return AuthProfile(
        id=f"{provider}:subscription",
        kind=CredentialKind.OAUTH,
        provider_family=provider,
        metadata={
            "token_expires_at": resolved_expires_at.isoformat(),
            "credential_backend": "test-keyring",
        },
        created_at=datetime.now(UTC),
        oauth_authorization_endpoint=f"https://auth.{provider}.example/authorize",
        oauth_token_endpoint=f"https://auth.{provider}.example/token",
        oauth_client_id=OPENAI_OAUTH_CLIENT_ID,
        oauth_scope_list=["model.request"],
        oauth_token_keyring_handle=f"{provider}:subscription:access",
        oauth_refresh_keyring_handle=f"{provider}:subscription:refresh",
    )
