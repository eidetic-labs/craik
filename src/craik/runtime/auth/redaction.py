"""Auth profile redaction helpers."""

from __future__ import annotations

from typing import Any

PUBLISHABLE_METADATA_KEYS = frozenset(
    {
        "allow_local_base_url",
        "base_url",
        "client_id",
        "credentials_path",
        "endpoint",
        "env_var",
        "manager",
        "model",
        "provider_family",
        "ref",
        "refresh_endpoint",
        "secret_ref",
        "secrets_root",
        "source",
    }
)


def masked_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Mask all metadata fields except reviewed non-secret references."""
    return {
        key: value if key in PUBLISHABLE_METADATA_KEYS else "***"
        for key, value in metadata.items()
    }
