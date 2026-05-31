"""Keyring-reference credential source."""

from __future__ import annotations

from dataclasses import dataclass

from craik.runtime.auth.profile import CredentialStatus
from craik.runtime.auth.sources.anthropic_env import anthropic_headers_for_credential
from craik.runtime.providers.provider_transport import (
    ProviderFamily,
    normalize_provider_family,
)
from craik.runtime.shell.credential_storage import CredentialStorageError, get_cached_credential


@dataclass(frozen=True)
class KeyringRefCredentialSource:
    """Resolve provider credentials from Craik's cached credential store."""

    ref: str
    credential_mode: str | None = None

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider-specific headers from cached credential material."""
        secret = self._resolve_secret()
        if family == "anthropic":
            return anthropic_headers_for_credential(secret, credential_mode=self.credential_mode)
        if normalize_provider_family(family) == "google":
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
