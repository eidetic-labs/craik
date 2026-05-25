"""Provider OAuth credential source backed by secure cached credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from craik.runtime.auth.profile import AuthProfile, CredentialStatus
from craik.runtime.auth.sources.anthropic_oauth import AnthropicOAuthClient
from craik.runtime.auth.sources.gemini_oauth import GeminiOAuthClient
from craik.runtime.auth.sources.openai_oauth import OpenAIOAuthClient
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.shell.credential_storage import (
    CredentialStorageError,
    get_cached_credential,
    put_cached_credential,
)


class ProviderOAuthCredentialError(RuntimeError):
    """Raised when a provider OAuth profile cannot produce headers."""


@dataclass(frozen=True)
class ProviderOAuthCredentialSource:
    """Resolve provider OAuth bearer tokens from Craik's cached credential store."""

    profile: AuthProfile

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider OAuth authorization headers, refreshing expired access tokens."""
        if family != self.profile.provider_family:
            raise ProviderOAuthCredentialError("OAuth profile provider family mismatch")
        access_token = self._access_token()
        if self._is_expired():
            access_token = self._refresh_access_token()
        return {"Authorization": f"Bearer {access_token}"}

    def status(self) -> CredentialStatus:
        """Check whether cached OAuth token handles resolve without exposing token material."""
        try:
            self._access_token()
            self._refresh_token()
        except CredentialStorageError as exc:
            return CredentialStatus(status="rejected", detail=str(exc))
        expires_at = self._expires_at()
        if expires_at is not None and expires_at <= datetime.now(UTC):
            return CredentialStatus(status="expired", expires_at=expires_at)
        return CredentialStatus(status="ok", expires_at=expires_at)

    def _access_token(self) -> str:
        handle = self.profile.oauth_token_keyring_handle
        if not handle:
            raise ProviderOAuthCredentialError("OAuth profile requires an access-token handle")
        credential = get_cached_credential(handle)
        if not credential.value:
            raise CredentialStorageError("OAuth access token could not be resolved")
        return credential.value

    def _refresh_token(self) -> str:
        handle = self.profile.oauth_refresh_keyring_handle
        if not handle:
            raise ProviderOAuthCredentialError("OAuth profile requires a refresh-token handle")
        credential = get_cached_credential(handle)
        if not credential.value:
            raise CredentialStorageError("OAuth refresh token could not be resolved")
        return credential.value

    def _refresh_access_token(self) -> str:
        access_handle = self.profile.oauth_token_keyring_handle
        refresh_handle = self.profile.oauth_refresh_keyring_handle
        if not access_handle or not refresh_handle:
            raise ProviderOAuthCredentialError("OAuth profile requires token handles")
        token_set, refresh_token = self._client().refresh_access_token(
            refresh_token=self._refresh_token()
        )
        put_cached_credential(access_handle, token_set.access_token)
        put_cached_credential(refresh_handle, refresh_token)
        return token_set.access_token

    def _client(self) -> OpenAIOAuthClient | AnthropicOAuthClient | GeminiOAuthClient:
        token_endpoint = self.profile.oauth_token_endpoint
        client_id = self.profile.oauth_client_id
        scope = tuple(self.profile.oauth_scope_list or ())
        if not token_endpoint or not client_id or not scope:
            raise ProviderOAuthCredentialError("OAuth profile is missing token metadata")
        if self.profile.provider_family == "openai":
            return OpenAIOAuthClient(
                token_endpoint=token_endpoint,
                client_id=client_id,
                scope=scope,
            )
        if self.profile.provider_family == "anthropic":
            return AnthropicOAuthClient(
                token_endpoint=token_endpoint,
                client_id=client_id,
                scope=scope,
            )
        if self.profile.provider_family == "gemini":
            return GeminiOAuthClient(
                token_endpoint=token_endpoint,
                client_id=client_id,
                scope=scope,
            )
        raise ProviderOAuthCredentialError("unsupported provider OAuth family")

    def _is_expired(self) -> bool:
        expires_at = self._expires_at()
        return expires_at is not None and expires_at <= datetime.now(UTC)

    def _expires_at(self) -> datetime | None:
        value = self.profile.metadata.get("token_expires_at")
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)


__all__ = [
    "ProviderOAuthCredentialError",
    "ProviderOAuthCredentialSource",
]
