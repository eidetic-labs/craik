"""Shared HMAC integrity helpers for operator-sensitive runtime records."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Protocol


class IntegrityStore(Protocol):
    """Store surface needed for local HMAC secret placement."""

    database_path: Path

_HMAC_SECRET_FILENAME = "instruction-approval-hmac.key"  # nosec B105
_OWNER_ONLY_FILE_MODE = 0o600


def hmac_key_for_store(store: IntegrityStore) -> bytes:
    """Return the per-store HMAC key, creating it with owner-only mode on POSIX."""
    secret = _approval_secret_path(store)
    secret.parent.mkdir(parents=True, exist_ok=True)
    if secret.exists():
        raw = secret.read_text(encoding="utf-8").strip()
    else:
        raw = secrets.token_hex(32)
        secret.write_text(f"{raw}\n", encoding="utf-8")
        if os.name == "posix":
            secret.chmod(_OWNER_ONLY_FILE_MODE)
    return hashlib.sha256(raw.encode("utf-8")).digest()


def contract_hmac(payload: dict[str, Any], key: bytes, *, field: str = "receipt_hmac") -> str:
    """Return a stable HMAC for a contract payload with the HMAC field omitted."""
    unsigned = dict(payload)
    unsigned.pop(field, None)
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def verify_contract_hmac(
    payload: dict[str, Any],
    key: bytes,
    *,
    field: str = "receipt_hmac",
) -> bool:
    """Return whether a payload carries a valid stable HMAC."""
    supplied = payload.get(field)
    if not isinstance(supplied, str) or not supplied:
        return False
    return hmac.compare_digest(supplied, contract_hmac(payload, key, field=field))


def _approval_secret_path(store: IntegrityStore) -> Path:
    home = store.database_path.parent.parent
    return home / "secrets" / _HMAC_SECRET_FILENAME
