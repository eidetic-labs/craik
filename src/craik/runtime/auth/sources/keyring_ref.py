"""Keyring-reference credential source."""

from __future__ import annotations

from dataclasses import dataclass

from craik.runtime.auth.profile import CredentialStatus
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.shell.credential_storage import CredentialStorageError, get_cached_credential


@dataclass(frozen=True)
class KeyringRefCredentialSource:
    """Resolve provider credentials from Craik's cached credential store."""

    ref: str

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider-specific headers from cached credential material."""
        secret = self._resolve_secret()
        if family == "anthropic":
            return {
                "anthropic-version": "2023-06-01",
                "x-api-key": secret,
            }
        if family == "gemini":
            return {"x-goog-api-key": secret}
        return {"Authorization": f"Bearer {secret}"}

    def status(self) -> CredentialStatus:
        """Check whether the keyring reference resolves without exposing it."""
        try:
            get_cached_credential(self.ref)
        except CredentialStorageError as exc:
            return CredentialStatus(status="rejected", detail=str(exc))
        return CredentialStatus(status="ok")

    def _resolve_secret(self) -> str:
        credential = get_cached_credential(self.ref)
        if not credential.value:
            raise CredentialStorageError("cached credential could not be resolved")
        return credential.value
