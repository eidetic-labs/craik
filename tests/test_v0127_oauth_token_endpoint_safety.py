from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources.provider_oauth import (
    ProviderOAuthCredentialError,
    ProviderOAuthCredentialSource,
)


@pytest.mark.parametrize(
    "token_endpoint",
    [
        "http://attacker.example/oauth/token",
        "file:///tmp/token",
        "https://127.0.0.1/oauth/token",
    ],
)
def test_refresh_rejects_unsafe_token_endpoint_before_secret_resolution(
    monkeypatch,
    token_endpoint: str,
) -> None:
    def _get_cached_credential(ref: str):
        raise AssertionError("unsafe token endpoint should fail before keyring access")

    monkeypatch.setattr(
        "craik.runtime.auth.sources.provider_oauth.get_cached_credential",
        _get_cached_credential,
    )

    source = ProviderOAuthCredentialSource(_oauth_profile(token_endpoint=token_endpoint))

    with pytest.raises(ProviderOAuthCredentialError, match="OAuth credential failed"):
        source._refresh_access_token()


def _oauth_profile(*, token_endpoint: str) -> AuthProfile:
    return AuthProfile(
        id="openai:subscription",
        kind=CredentialKind.OAUTH,
        provider_family="openai",
        metadata={
            "token_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "credential_backend": "test-keyring",
        },
        created_at=datetime.now(UTC),
        oauth_authorization_endpoint="https://auth.openai.example/authorize",
        oauth_token_endpoint=token_endpoint,
        oauth_client_id="registered-client",
        oauth_scope_list=["openid", "profile", "email", "offline_access"],
        oauth_token_keyring_handle="openai:subscription:access",
        oauth_refresh_keyring_handle="openai:subscription:refresh",
    )
