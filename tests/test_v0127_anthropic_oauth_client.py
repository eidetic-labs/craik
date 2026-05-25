from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from craik.runtime.auth.oauth_loopback import generate_pkce_challenge
from craik.runtime.auth.profile import CredentialKind
from craik.runtime.auth.sources import anthropic_oauth
from craik.runtime.auth.sources.anthropic_oauth import (
    ANTHROPIC_OAUTH_BILLING_SURFACE,
    ANTHROPIC_OAUTH_CLIENT_ID,
    ANTHROPIC_OAUTH_SCOPES,
    ANTHROPIC_OAUTH_TOKEN_ENDPOINT,
    AnthropicOAuthClient,
    AnthropicOAuthError,
    AnthropicOAuthTokenSet,
    store_anthropic_oauth_profile,
)
from craik.runtime.shell.credential_storage import CredentialStorageStatus


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_anthropic_oauth_authorization_url_uses_state_pkce_and_scope() -> None:
    pkce = generate_pkce_challenge()
    client = AnthropicOAuthClient()

    url = client.authorization_url(
        redirect_uri="http://127.0.0.1:54321/oauth/callback",
        state="state-value",
        pkce=pkce,
    )

    params = parse_qs(urlparse(url).query)
    assert params["client_id"] == [ANTHROPIC_OAUTH_CLIENT_ID]
    assert params["state"] == ["state-value"]
    assert params["code_challenge"] == [pkce.challenge]
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == [" ".join(ANTHROPIC_OAUTH_SCOPES)]


def test_anthropic_oauth_exchange_code_posts_verifier_without_persisting_it() -> None:
    seen: dict[str, Any] = {}
    pkce = generate_pkce_challenge()
    client = AnthropicOAuthClient()
    now = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    def _opener(request: Request, *, timeout: float) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["form"] = parse_qs((request.data or b"").decode("utf-8"))
        return _FakeResponse(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 900,
                "scope": "models.read messages.create",
            }
        )

    token_set, refresh_value = client.exchange_code(
        code="auth-code",
        redirect_uri="http://127.0.0.1:54321/oauth/callback",
        pkce=pkce,
        opener=_opener,
        now=now,
    )

    assert seen["url"] == ANTHROPIC_OAUTH_TOKEN_ENDPOINT
    assert seen["form"]["grant_type"] == ["authorization_code"]
    assert seen["form"]["code"] == ["auth-code"]
    assert seen["form"]["code_verifier"] == [pkce.verifier]
    assert token_set.access_token == "access-token"
    assert refresh_value == "refresh-token"
    assert token_set.expires_at == now + timedelta(seconds=900)
    assert token_set.scope == ["models.read", "messages.create"]


def test_anthropic_oauth_refresh_posts_refresh_token_as_local_value() -> None:
    seen: dict[str, Any] = {}
    client = AnthropicOAuthClient()

    def _opener(request: Request, *, timeout: float) -> _FakeResponse:
        seen["form"] = parse_qs((request.data or b"").decode("utf-8"))
        return _FakeResponse(
            {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600,
            }
        )

    token_set, refresh_value = client.refresh_access_token(
        refresh_token="old-refresh-token",
        opener=_opener,
    )

    assert seen["form"]["grant_type"] == ["refresh_token"]
    assert seen["form"]["refresh_token"] == ["old-refresh-token"]
    assert token_set.access_token == "new-access-token"
    assert refresh_value == "new-refresh-token"


def test_anthropic_oauth_rejects_token_response_without_refresh_token() -> None:
    def _opener(request: Request, *, timeout: float) -> _FakeResponse:
        return _FakeResponse({"access_token": "access-token"})

    with pytest.raises(AnthropicOAuthError, match="refresh token"):
        AnthropicOAuthClient().refresh_access_token(refresh_token="old", opener=_opener)


def test_store_anthropic_oauth_profile_writes_access_and_refresh_handles(monkeypatch) -> None:
    stored: dict[str, str] = {}

    monkeypatch.setattr(
        anthropic_oauth.credential_storage,
        "credential_storage_status",
        lambda env=None: CredentialStorageStatus(
            backend="test-keyring",
            status="available",
            secure=True,
        ),
    )
    monkeypatch.setattr(
        anthropic_oauth.credential_storage,
        "put_cached_credential",
        lambda ref, value, *, env=None: stored.__setitem__(ref, value),
    )

    token_set = AnthropicOAuthTokenSet(
        access_token="access-token",
        expires_at=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        scope=["models.read"],
    )

    profile = store_anthropic_oauth_profile(
        token_set,
        refresh_token="refresh-token",
        profile_id="anthropic:subscription",
    )

    assert profile.kind is CredentialKind.OAUTH
    assert profile.oauth_token_keyring_handle == "anthropic:subscription:oauth-access-token"
    assert profile.oauth_refresh_keyring_handle == "anthropic:subscription:oauth-refresh-token"
    assert stored == {
        "anthropic:subscription:oauth-access-token": "access-token",
        "anthropic:subscription:oauth-refresh-token": "refresh-token",
    }
    assert profile.metadata["billing_surface"] == ANTHROPIC_OAUTH_BILLING_SURFACE


def test_store_anthropic_oauth_profile_requires_secure_keyring(monkeypatch) -> None:
    monkeypatch.setattr(
        anthropic_oauth.credential_storage,
        "credential_storage_status",
        lambda env=None: CredentialStorageStatus(
            backend="file",
            status="fallback",
            secure=False,
        ),
    )
    token_set = AnthropicOAuthTokenSet(
        access_token="access-token",
        expires_at=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        scope=["models.read"],
    )

    with pytest.raises(AnthropicOAuthError, match="OS keyring"):
        store_anthropic_oauth_profile(token_set, refresh_token="refresh-token")
