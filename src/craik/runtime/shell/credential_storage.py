"""Credential storage posture helpers.

The v0.10.0 UX exposes secure-storage status without adding a hard dependency on
platform keychain libraries. Secret material remains outside these helpers.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from typing import Literal

CredentialBackendStatus = Literal["available", "unavailable", "fallback"]


@dataclass(frozen=True)
class CredentialStorageStatus:
    """Redacted credential storage posture."""

    backend: str
    status: CredentialBackendStatus
    secure: bool
    warning: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "status": self.status,
            "secure": self.secure,
            "warning": self.warning,
        }


def credential_storage_status(env: dict[str, str] | None = None) -> CredentialStorageStatus:
    """Return the best available credential storage posture for this platform."""
    values = os.environ if env is None else env
    forced = values.get("CRAIK_CREDENTIAL_BACKEND")
    if forced == "file":
        return _file_fallback()
    system = platform.system().lower()
    if system == "darwin":
        return CredentialStorageStatus(backend="macos-keychain", status="available", secure=True)
    if system == "windows":
        return CredentialStorageStatus(
            backend="windows-credential-manager",
            status="available",
            secure=True,
        )
    if system == "linux":
        return CredentialStorageStatus(
            backend="secret-service",
            status="unavailable",
            secure=False,
            warning=(
                "Secret Service availability is runtime-dependent; Craik will use explicit "
                "secret references or file-backed fallback until a keyring backend is configured."
            ),
        )
    return _file_fallback()


def _file_fallback() -> CredentialStorageStatus:
    return CredentialStorageStatus(
        backend="file",
        status="fallback",
        secure=False,
        warning="file-backed secret references require owner-only filesystem permissions",
    )
