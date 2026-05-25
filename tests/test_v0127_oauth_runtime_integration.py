from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.login import AuthCaptureResult, OAuthLoginResult, auth_status_rows
from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources import (
    ProviderOAuthCredentialSource,
    provider_oauth,
    source_for_auth_profile,
)
from craik.runtime.auth.sources.openai_oauth import OpenAIOAuthTokenSet
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
    assert row["redacted"] is True


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


def profile_runtime_ok():
    from craik.runtime.auth.profile import CredentialStatus

    return CredentialStatus(status="ok")


def _oauth_profile(expires_at: datetime | None = None) -> AuthProfile:
    resolved_expires_at = expires_at or datetime.now(UTC) + timedelta(hours=1)
    return AuthProfile(
        id="openai:subscription",
        kind=CredentialKind.OAUTH,
        provider_family="openai",
        metadata={
            "token_expires_at": resolved_expires_at.isoformat(),
            "credential_backend": "test-keyring",
        },
        created_at=datetime.now(UTC),
        oauth_authorization_endpoint="https://auth.openai.example/authorize",
        oauth_token_endpoint="https://auth.openai.example/token",
        oauth_client_id="craik-cli",
        oauth_scope_list=["model.request"],
        oauth_token_keyring_handle="openai:subscription:access",
        oauth_refresh_keyring_handle="openai:subscription:refresh",
    )
