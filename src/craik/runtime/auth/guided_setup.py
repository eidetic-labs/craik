"""Guided provider authentication setup helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from craik.runtime.auth.pool import CredentialPoolConfig, CredentialPoolEntry
from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.local_models import local_model_base_url_warnings
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.providers.provider_url_safety import assert_safe_provider_url

GUIDED_PROVIDER_DEFAULTS = {
    "openai": {
        "family": "openai",
        "profile_id": "openai:default",
        "env_var": "CRAIK_OPENAI_API_KEY",
        "base_url": "https://api.openai.com",
    },
    "anthropic": {
        "family": "anthropic",
        "profile_id": "anthropic:default",
        "env_var": "CRAIK_ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com",
    },
    "gemini": {
        "family": "gemini",
        "profile_id": "gemini:default",
        "env_var": "CRAIK_GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com",
    },
    "local": {
        "family": "chat_completions",
        "profile_id": "chat_completions:local",
        "env_var": "LOCAL_OPENAI_COMPATIBLE_API_KEY",
        "base_url": "http://localhost:11434/v1",
        "allow_local_base_url": True,
    },
}
DEFAULT_REF_MANAGER = "env"
FILE_REF_MANAGER = "file"


def guided_provider_defaults(provider: str) -> dict[str, Any]:
    """Return normalized defaults for a guided auth setup provider."""
    key = provider.strip().lower()
    try:
        return cast(dict[str, Any], GUIDED_PROVIDER_DEFAULTS[key])
    except KeyError as exc:
        allowed = ", ".join(sorted(GUIDED_PROVIDER_DEFAULTS))
        raise ValueError(f"unsupported provider; expected one of: {allowed}") from exc


def build_guided_auth_profile(
    defaults: dict[str, Any],
    *,
    profile_id: str | None,
    env_var: str | None,
    secret_ref: str | None,
    ref_manager: str,
    secrets_root: str | None,
    base_url: str | None,
    allow_local_base_url: bool,
) -> AuthProfile:
    """Build and validate the auth profile for guided provider setup."""
    if env_var and secret_ref:
        raise ValueError("choose either --env-var or --secret-ref, not both")
    family = cast(ProviderFamily, defaults["family"])
    resolved_profile_id = profile_id or str(defaults["profile_id"])
    resolved_base_url = base_url or str(defaults["base_url"])
    allow_local = bool(defaults.get("allow_local_base_url")) or allow_local_base_url
    assert_safe_provider_url(resolved_base_url, allow_local=allow_local)
    metadata: dict[str, Any] = {"base_url": resolved_base_url}
    if allow_local:
        metadata["allow_local_base_url"] = True
    if secret_ref:
        if ref_manager == FILE_REF_MANAGER and not secrets_root:
            raise ValueError("--secrets-root is required when --secret-manager=file")
        if ref_manager == FILE_REF_MANAGER and Path(secret_ref).expanduser().is_absolute():
            raise ValueError("file secret refs must be relative to the secrets root")
        metadata.update({"manager": ref_manager, "ref": secret_ref})
        if secrets_root:
            metadata["secrets_root"] = secrets_root
        kind = CredentialKind.SECRET_REF
    else:
        metadata["env_var"] = env_var or str(defaults["env_var"])
        kind = CredentialKind.API_KEY
    return AuthProfile(
        id=resolved_profile_id,
        kind=kind,
        provider_family=family,
        metadata=metadata,
        created_at=datetime.now(UTC),
    )


def default_pool_for_profile(profile: AuthProfile) -> CredentialPoolConfig:
    """Build the default credential pool for a guided auth profile."""
    return CredentialPoolConfig(
        id=f"{profile.provider_family}:default",
        provider_family=profile.provider_family,
        profiles=[CredentialPoolEntry(profile_id=profile.id)],
    )


def credential_guidance(profile: AuthProfile, status: CredentialStatus) -> list[str]:
    """Return actionable next steps for a guided auth setup result."""
    guidance: list[str] = []
    if profile.kind is CredentialKind.API_KEY:
        env_var = profile.metadata.get("env_var")
        if status.status != "ok" and isinstance(env_var, str):
            guidance.append(f"Set {env_var} before running live provider calls.")
    elif profile.kind is CredentialKind.SECRET_REF and status.status != "ok":
        guidance.append("Verify the configured secret reference resolves before live use.")
    if profile.provider_family == "chat_completions":
        base_url = profile.metadata.get("base_url")
        if isinstance(base_url, str):
            guidance.extend(local_model_base_url_warnings(base_url))
        guidance.append("Confirm the local OpenAI-compatible server is listening at base_url.")
    return guidance


__all__ = [
    "DEFAULT_REF_MANAGER",
    "FILE_REF_MANAGER",
    "build_guided_auth_profile",
    "credential_guidance",
    "default_pool_for_profile",
    "guided_provider_defaults",
]
