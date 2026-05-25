from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources import provider_oauth
from craik.runtime.auth.sources.openai_oauth import OpenAIOAuthError
from craik.runtime.auth.sources.provider_oauth import (
    ProviderOAuthCredentialError,
    ProviderOAuthCredentialSource,
)
from craik.runtime.shell.credential_storage import StoredCredential


def test_refresh_failure_emits_provider_remediation(monkeypatch) -> None:
    stored = {
        "openai:subscription:access": "expired-access",
        "openai:subscription:refresh": "stored-refresh",
    }

    class _Client:
        def refresh_access_token(self, *, refresh_token: str):
            assert refresh_token == "stored-refresh"
            raise OpenAIOAuthError("invalid_grant")

    monkeypatch.setattr(
        provider_oauth,
        "get_cached_credential",
        lambda ref: StoredCredential(value=stored[ref], backend="test", secure=True),
    )
    monkeypatch.setattr(
        provider_oauth.ProviderOAuthCredentialSource,
        "_client",
        lambda self: _Client(),
    )

    with pytest.raises(ProviderOAuthCredentialError) as exc_info:
        ProviderOAuthCredentialSource(
            _oauth_profile(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        ).headers_for("openai")

    message = str(exc_info.value)
    assert "Openai OAuth credential could not be refreshed" in message
    assert "Re-run: craik auth login openai" in message


def test_refresh_rejects_non_https_token_endpoint_before_secret_resolution(monkeypatch) -> None:
    called = False

    def _get_cached_credential(ref: str) -> StoredCredential:
        nonlocal called
        called = True
        return StoredCredential(value=f"value-for-{ref}", backend="test", secure=True)

    monkeypatch.setattr(provider_oauth, "get_cached_credential", _get_cached_credential)

    with pytest.raises(ProviderOAuthCredentialError) as exc_info:
        ProviderOAuthCredentialSource(
            _oauth_profile(
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
                token_endpoint="http://attacker.example/oauth/token",
            )
        )._refresh_access_token()

    message = str(exc_info.value)
    assert "provider base_url must use HTTPS" in message
    assert "Re-run: craik auth login openai" in message
    assert called is False


def _oauth_profile(
    *,
    expires_at: datetime,
    token_endpoint: str = "https://auth.openai.example/token",
) -> AuthProfile:
    return AuthProfile(
        id="openai:subscription",
        kind=CredentialKind.OAUTH,
        provider_family="openai",
        metadata={
            "token_expires_at": expires_at.isoformat(),
            "credential_backend": "test-keyring",
        },
        created_at=datetime.now(UTC),
        oauth_authorization_endpoint="https://auth.openai.example/authorize",
        oauth_token_endpoint=token_endpoint,
        oauth_client_id="craik-cli",
        oauth_scope_list=["openid"],
        oauth_token_keyring_handle="openai:subscription:access",
        oauth_refresh_keyring_handle="openai:subscription:refresh",
    )
