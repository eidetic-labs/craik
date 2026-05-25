from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources.anthropic_oauth import (
    ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT,
    ANTHROPIC_OAUTH_TOKEN_ENDPOINT,
)
from craik.runtime.auth.sources.openai_oauth import (
    OPENAI_OAUTH_AUTHORIZATION_ENDPOINT,
    OPENAI_OAUTH_TOKEN_ENDPOINT,
)


def test_openai_oauth_profile_requires_complete_provider_oauth_fields() -> None:
    with pytest.raises(ValidationError, match="oauth auth profiles require"):
        _provider_oauth_profile(
            "openai",
            token_endpoint=None,
            refresh_handle=None,
        )


def test_openai_oauth_profile_validates_with_registered_metadata_shape() -> None:
    profile = _provider_oauth_profile(
        "openai",
        authorization_endpoint=OPENAI_OAUTH_AUTHORIZATION_ENDPOINT,
        token_endpoint=OPENAI_OAUTH_TOKEN_ENDPOINT,
        scopes=["openid", "profile", "email", "offline_access"],
    )

    assert profile.provider_family == "openai"
    assert profile.oauth_scope_list == ["openid", "profile", "email", "offline_access"]


def test_anthropic_oauth_profile_validates_with_documented_endpoints() -> None:
    profile = _provider_oauth_profile(
        "anthropic",
        authorization_endpoint=ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT,
        token_endpoint=ANTHROPIC_OAUTH_TOKEN_ENDPOINT,
    )

    assert profile.oauth_authorization_endpoint == "https://claude.ai/oauth/authorize"
    assert profile.oauth_token_endpoint == "https://console.anthropic.com/v1/oauth/token"


def test_gemini_adc_oauth_profile_validates_without_keyring_handles() -> None:
    profile = AuthProfile(
        id="gemini:vertex",
        kind=CredentialKind.OAUTH,
        provider_family="gemini",
        metadata={"credential_source": "adc", "gcp_project_id": "craik-project"},
        created_at=datetime.now(UTC),
        oauth_scope_list=["https://www.googleapis.com/auth/cloud-platform"],
    )

    assert profile.oauth_token_keyring_handle is None
    assert profile.oauth_refresh_keyring_handle is None


def test_gemini_service_account_oauth_profile_requires_service_account_path() -> None:
    with pytest.raises(ValidationError, match="service_account_path"):
        AuthProfile(
            id="gemini:vertex",
            kind=CredentialKind.OAUTH,
            provider_family="gemini",
            metadata={"credential_source": "service_account", "gcp_project_id": "craik-project"},
            created_at=datetime.now(UTC),
            oauth_scope_list=["https://www.googleapis.com/auth/cloud-platform"],
        )


def _provider_oauth_profile(
    provider: str,
    *,
    authorization_endpoint: str | None = "https://auth.example.test/authorize",
    token_endpoint: str | None = "https://auth.example.test/token",
    scopes: list[str] | None = None,
    refresh_handle: str | None = "refresh-handle",
) -> AuthProfile:
    return AuthProfile(
        id=f"{provider}:subscription",
        kind=CredentialKind.OAUTH,
        provider_family=provider,
        created_at=datetime.now(UTC),
        oauth_authorization_endpoint=authorization_endpoint,
        oauth_token_endpoint=token_endpoint,
        oauth_client_id="registered-client",
        oauth_scope_list=scopes or ["model.request"],
        oauth_token_keyring_handle="access-handle",
        oauth_refresh_keyring_handle=refresh_handle,
    )
