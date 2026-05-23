"""Credential storage posture helpers.

The v0.10.0 UX exposes secure-storage status without adding a hard dependency on
platform keychain libraries. Secret material remains outside these helpers.
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, cast

from craik.runtime.paths import resolve_craik_home

CredentialBackendStatus = Literal["available", "unavailable", "fallback"]
OWNER_ONLY_FILE_MODE = 0o600


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
    if _python_keyring_available():
        return CredentialStorageStatus(
            backend=_platform_keyring_name(),
            status="available",
            secure=True,
        )
    system = platform.system().lower()
    if system == "darwin":
        return CredentialStorageStatus(
            backend="macos-keychain",
            status="unavailable",
            secure=False,
            warning="install the optional keyring backend or set CRAIK_CREDENTIAL_BACKEND=file",
        )
    if system == "windows":
        return CredentialStorageStatus(
            backend="windows-credential-manager",
            status="unavailable",
            secure=False,
            warning="install the optional keyring backend or set CRAIK_CREDENTIAL_BACKEND=file",
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


@dataclass(frozen=True)
class StoredCredential:
    """Resolved credential material plus backend provenance."""

    value: str
    backend: str
    secure: bool
    warning: str | None = None


class CredentialStorageError(RuntimeError):
    """Raised when cached credential material cannot be stored or resolved."""


def put_cached_credential(
    ref: str,
    value: str,
    *,
    env: dict[str, str] | None = None,
) -> CredentialStorageStatus:
    """Store credential material behind an opaque keyring reference."""
    if not ref.strip():
        raise CredentialStorageError("credential reference is required")
    if not value:
        raise CredentialStorageError("credential value is required")
    status = credential_storage_status(env)
    if status.secure and _python_keyring_available():
        _keyring_set(ref, value)
        return status
    _file_put(ref, value, env=env)
    return _file_fallback()


def get_cached_credential(ref: str, *, env: dict[str, str] | None = None) -> StoredCredential:
    """Resolve cached credential material without exposing it to callers unless needed."""
    if not ref.strip():
        raise CredentialStorageError("credential reference is required")
    status = credential_storage_status(env)
    if status.secure and _python_keyring_available():
        value = _keyring_get(ref)
        if not value:
            raise CredentialStorageError("cached credential could not be resolved")
        return StoredCredential(value=value, backend=status.backend, secure=True)
    payload = _file_read(env=env)
    value = payload.get(ref)
    if not isinstance(value, str) or not value:
        raise CredentialStorageError("cached credential could not be resolved")
    fallback = _file_fallback()
    return StoredCredential(
        value=value,
        backend=fallback.backend,
        secure=fallback.secure,
        warning=fallback.warning,
    )


def delete_cached_credential(ref: str, *, env: dict[str, str] | None = None) -> None:
    """Delete cached credential material for one opaque reference."""
    status = credential_storage_status(env)
    if status.secure and _python_keyring_available():
        _keyring_delete(ref)
        return
    payload = _file_read(env=env)
    payload.pop(ref, None)
    _file_write(payload, env=env)


def _file_fallback() -> CredentialStorageStatus:
    return CredentialStorageStatus(
        backend="file",
        status="fallback",
        secure=False,
        warning="file-backed secret references require owner-only filesystem permissions",
    )


def _platform_keyring_name() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos-keychain"
    if system == "windows":
        return "windows-credential-manager"
    if system == "linux":
        return "secret-service"
    return "python-keyring"


def _python_keyring_available() -> bool:
    try:
        import_module("keyring")
    except Exception:
        return False
    return True


def _keyring_service() -> str:
    return "craik"


def _keyring_set(ref: str, value: str) -> None:
    try:
        keyring = _keyring_module()

        keyring.set_password(_keyring_service(), ref, value)
    except Exception as exc:
        raise CredentialStorageError("keyring credential write failed") from exc


def _keyring_get(ref: str) -> str | None:
    try:
        keyring = _keyring_module()

        return cast(str | None, keyring.get_password(_keyring_service(), ref))
    except Exception as exc:
        raise CredentialStorageError("keyring credential read failed") from exc


def _keyring_delete(ref: str) -> None:
    try:
        keyring = _keyring_module()

        keyring.delete_password(_keyring_service(), ref)
    except Exception:
        return


def _keyring_module() -> Any:
    return import_module("keyring")


def _file_path(env: dict[str, str] | None = None) -> Path:
    return resolve_craik_home(env) / "credential-cache.json"


def _file_read(env: dict[str, str] | None = None) -> dict[str, str]:
    path = _file_path(env)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialStorageError("credential cache contains invalid data") from exc
    if not isinstance(payload, dict):
        raise CredentialStorageError("credential cache contains invalid data")
    return {str(key): str(value) for key, value in payload.items() if isinstance(value, str)}


def _file_put(ref: str, value: str, *, env: dict[str, str] | None = None) -> None:
    payload = _file_read(env=env)
    payload[ref] = value
    _file_write(payload, env=env)


def _file_write(payload: dict[str, str], *, env: dict[str, str] | None = None) -> None:
    path = _file_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".credential-cache.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        if os.name == "posix":
            temp_path.chmod(OWNER_ONLY_FILE_MODE)
        os.replace(temp_path, path)
        if os.name == "posix":
            path.chmod(OWNER_ONLY_FILE_MODE)
    finally:
        if temp_path.exists():
            temp_path.unlink()
