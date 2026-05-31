"""Secret-reference credential source.

Secret managers implement the small ``SecretManager`` protocol so deployments
can plug in Vault, AWS Secrets Manager, cloud KMS brokers, or internal secret
services without changing Craik's provider runtime. Built-in managers cover
environment variables and local files for development and tests.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from craik.runtime.auth.profile import CredentialStatus
from craik.runtime.providers.provider_transport import (
    ProviderFamily,
    normalize_provider_family,
)
from craik.runtime.secrets import SecretNotFoundError, SecretRef, SecretResolver


class SecretRefCredentialError(RuntimeError):
    """Raised when a secret-reference credential cannot resolve."""


SECRET_REFERENCE_ERROR = "secret reference could not be resolved"


class SecretManager(Protocol):
    """Resolve an opaque secret reference into credential material."""

    def resolve(self, ref: str) -> str:
        """Return credential material for a reference."""
        raise NotImplementedError


@dataclass(frozen=True)
class EnvVarSecretManager:
    """Secret manager that treats refs as environment variable names."""

    resolver: SecretResolver = SecretResolver()

    def resolve(self, ref: str) -> str:
        """Resolve a secret from an environment variable."""
        try:
            return self.resolver.resolve(SecretRef(env_var=ref))
        except SecretNotFoundError as exc:
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR) from exc


@dataclass(frozen=True)
class FileSecretManager:
    """Secret manager that reads credential material below a configured root."""

    secrets_root: Path

    def resolve(self, ref: str) -> str:
        """Resolve a secret from a root-relative file path."""
        path = self._validated_secret_path(ref)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR) from exc
        if not value:
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR)
        return value

    def _validated_secret_path(self, ref: str) -> Path:
        root = self.secrets_root.expanduser().resolve(strict=False)
        candidate = (root / ref).expanduser()
        try:
            metadata = candidate.lstat()
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR)
        if not resolved.is_relative_to(root):
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR)
        if os.name == "posix" and metadata.st_mode & 0o077:
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR)
        return resolved


@dataclass(frozen=True)
class SecretRefCredentialSource:
    """Resolve provider credentials through a pluggable secret manager."""

    ref: str
    manager: SecretManager

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider-specific headers from a resolved secret reference."""
        secret = self._resolve_secret()
        if family == "anthropic":
            return {
                "anthropic-version": "2023-06-01",
                "x-api-key": secret,
            }
        if normalize_provider_family(family) == "google":
            return {"x-goog-api-key": secret}
        return {"Authorization": f"Bearer {secret}"}

    def status(self) -> CredentialStatus:
        """Check whether the secret reference resolves without exposing it."""
        try:
            self._resolve_secret()
        except SecretRefCredentialError as exc:
            return CredentialStatus(status="rejected", detail=str(exc))
        return CredentialStatus(status="ok")

    def _resolve_secret(self) -> str:
        secret = self.manager.resolve(self.ref)
        if not secret:
            raise SecretRefCredentialError(SECRET_REFERENCE_ERROR)
        return secret
