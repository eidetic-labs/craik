"""Provider OAuth credential source backed by secure cached credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from craik.runtime.auth.profile import AuthProfile, CredentialStatus
from craik.runtime.auth.sources.anthropic_oauth import AnthropicOAuthClient, AnthropicOAuthError
from craik.runtime.auth.sources.google_oauth import GoogleOAuthError, headers_for_profile
from craik.runtime.auth.sources.openai_oauth import OpenAIOAuthClient, OpenAIOAuthError
from craik.runtime.providers.provider_transport import (
    ProviderFamily,
    normalize_provider_family,
)
from craik.runtime.providers.provider_url_safety import (
    ProviderURLSafetyError,
    assert_safe_provider_url,
)
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
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential failed: "
                "profile provider family mismatch. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
        if normalize_provider_family(
            self.profile.provider_family
        ) == "google" and self.profile.metadata.get("credential_source") in {
            "adc",
            "service_account",
        }:
            try:
                return headers_for_profile(self.profile)
            except GoogleOAuthError as exc:
                raise ProviderOAuthCredentialError(
                    "Your Gemini OAuth credential could not be resolved. "
                    "Re-run: craik auth login google"
                ) from exc
        access_token = self._access_token()
        if self._is_expired():
            access_token = self._refresh_access_token()
        if self.profile.provider_family == "anthropic":
            return {"x-api-key": access_token}
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
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential failed: "
                "profile requires an access-token handle. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
        credential = get_cached_credential(handle)
        if not credential.value:
            raise CredentialStorageError(
                f"Your {_provider_label(self.profile)} OAuth access token could not be resolved. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
        return credential.value

    def _refresh_token(self) -> str:
        handle = self.profile.oauth_refresh_keyring_handle
        if not handle:
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential failed: "
                "profile requires a refresh-token handle. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
        credential = get_cached_credential(handle)
        if not credential.value:
            raise CredentialStorageError(
                f"Your {_provider_label(self.profile)} OAuth refresh token could not be resolved. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
        return credential.value

    def _refresh_access_token(self) -> str:
        access_handle = self.profile.oauth_token_keyring_handle
        refresh_handle = self.profile.oauth_refresh_keyring_handle
        token_endpoint = self.profile.oauth_token_endpoint
        if not token_endpoint:
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential failed: "
                "profile is missing token endpoint metadata. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
        try:
            assert_safe_provider_url(token_endpoint, allow_local=False)
        except ProviderURLSafetyError as exc:
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential failed: {exc}. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            ) from exc
        if not access_handle or not refresh_handle:
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential failed: "
                "profile requires token handles. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
        try:
            token_set, refresh_token = self._client().refresh_access_token(
                refresh_token=self._refresh_token()
            )
        except (
            ProviderOAuthCredentialError,
            CredentialStorageError,
            OpenAIOAuthError,
            AnthropicOAuthError,
            GoogleOAuthError,
        ) as exc:
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential could not be "
                f"refreshed. Re-run: craik auth login {self.profile.provider_family}"
            ) from exc
        put_cached_credential(access_handle, token_set.access_token)
        put_cached_credential(refresh_handle, refresh_token)
        return token_set.access_token

    def _client(self) -> OpenAIOAuthClient | AnthropicOAuthClient:
        token_endpoint = self.profile.oauth_token_endpoint
        client_id = self.profile.oauth_client_id
        scope = tuple(self.profile.oauth_scope_list or ())
        if not token_endpoint or not client_id or not scope:
            raise ProviderOAuthCredentialError(
                f"Your {_provider_label(self.profile)} OAuth credential failed: "
                "profile is missing token metadata. "
                f"Re-run: craik auth login {self.profile.provider_family}"
            )
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
        raise ProviderOAuthCredentialError(
            f"Your {_provider_label(self.profile)} OAuth credential failed: "
            "unsupported provider OAuth family. "
            f"Re-run: craik auth login {self.profile.provider_family}"
        )

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


def _provider_label(profile: AuthProfile) -> str:
    return profile.provider_family.replace("_", " ").title()


__all__ = [
    "ProviderOAuthCredentialError",
    "ProviderOAuthCredentialSource",
]
