"""Capture-and-cache provider auth flows."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from craik.runtime.auth.guided_setup import (
    DEFAULT_REF_MANAGER,
    build_guided_auth_profile,
    default_pool_for_profile,
    guided_provider_defaults,
)
from craik.runtime.auth.health_check import health_check_profile_secret
from craik.runtime.auth.pool import CredentialPool
from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.auth.sanitization import sanitize_credential_error
from craik.runtime.auth.sources import source_for_auth_profile
from craik.runtime.auth.store import AuthProfileStore, AuthProfileStoreError
from craik.runtime.auth.visibility import active_operator_session_from_env, visible_auth_profiles
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.shell.credential_storage import (
    FILE_BACKED_CREDENTIAL_WARNING,
    CredentialStorageError,
    CredentialStorageStatus,
    credential_storage_status,
    delete_cached_credential,
    get_cached_credential,
    put_cached_credential,
)

CredentialPrompt = Callable[[str], str]
ConfirmPrompt = Callable[[str], bool]


@dataclass(frozen=True)
class AuthCaptureResult:
    """Redacted result for one provider login attempt."""

    provider: str
    profile: AuthProfile
    status: CredentialStatus
    credential_storage: CredentialStorageStatus
    reauthenticated: bool = False
    dry_run: bool = False
    warning: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe payload without credential material."""
        return {
            "provider": self.provider,
            "profile_id": self.profile.id,
            "provider_family": self.profile.provider_family,
            "kind": self.profile.kind,
            "status": self.status.model_dump(mode="json"),
            "credential_storage": self.credential_storage.as_dict(),
            "reauthenticated": self.reauthenticated,
            "dry_run": self.dry_run,
            "warning": self.warning,
            "redacted": True,
        }


@dataclass(frozen=True)
class AuthStatusRow:
    """Redacted auth status row shared by CLI, TUI, dashboard, and readiness."""

    id: str
    provider_family: ProviderFamily
    kind: CredentialKind
    backend: str | None
    last_validated_at: str | None
    health_status: str
    detail: str | None = None
    warning: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe auth status row."""
        return {
            "id": self.id,
            "provider_family": self.provider_family,
            "kind": self.kind,
            "backend": self.backend,
            "last_validated_at": self.last_validated_at,
            "health_status": self.health_status,
            "detail": self.detail,
            "warning": self.warning,
            "redacted": True,
        }


def capture_and_cache_login(
    provider: str,
    *,
    credential: str,
    profile_id: str | None = None,
    base_url: str | None = None,
    allow_local_base_url: bool = False,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> AuthCaptureResult:
    """Create a keyring-ref auth profile after capturing credential material."""
    defaults = guided_provider_defaults(provider)
    profile = _build_keyring_profile(
        provider,
        defaults=defaults,
        profile_id=profile_id,
        base_url=base_url,
        allow_local_base_url=allow_local_base_url,
    )
    status = health_check_profile_secret(profile, credential, env=env)
    if status.status != "ok":
        return AuthCaptureResult(
            provider=provider,
            profile=profile,
            status=status,
            credential_storage=credential_storage_status(env),
            dry_run=dry_run,
        )
    storage_status = credential_storage_status(env)
    warning = storage_status.warning
    if not dry_run:
        storage_status = put_cached_credential(
            _credential_ref(profile),
            credential,
            env=env,
        )
        metadata = dict(profile.metadata)
        metadata["last_validated_at"] = datetime.now(UTC).isoformat()
        metadata["credential_backend"] = storage_status.backend
        profile = profile.model_copy(update={"metadata": metadata, "last_status": "ok"})
        AuthProfileStore.from_env(env).put(profile)
        CredentialPool.from_env().put(default_pool_for_profile(profile))
        warning = storage_status.warning
    return AuthCaptureResult(
        provider=provider,
        profile=profile,
        status=status,
        credential_storage=storage_status,
        dry_run=dry_run,
        warning=warning,
    )


def explicit_reference_login(
    provider: str,
    *,
    env_var: str | None,
    secret_ref: str | None,
    profile_id: str | None = None,
    base_url: str | None = None,
    allow_local_base_url: bool = False,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> AuthCaptureResult:
    """Create an env-var or secret-ref profile for automation use cases."""
    defaults = guided_provider_defaults(provider)
    profile = build_guided_auth_profile(
        defaults,
        profile_id=profile_id,
        env_var=env_var,
        secret_ref=secret_ref,
        ref_manager=DEFAULT_REF_MANAGER,
        secrets_root=None,
        base_url=base_url,
        allow_local_base_url=allow_local_base_url,
    )
    status = profile_runtime_status(profile, env=env)
    if not dry_run:
        AuthProfileStore.from_env(env).put(profile)
        CredentialPool.from_env().put(default_pool_for_profile(profile))
    return AuthCaptureResult(
        provider=provider,
        profile=profile,
        status=status,
        credential_storage=credential_storage_status(env),
        dry_run=dry_run,
    )


def profile_runtime_status(
    profile: AuthProfile,
    *,
    env: dict[str, str] | None = None,
) -> CredentialStatus:
    """Return whether a profile's configured credential source resolves."""
    if profile.kind is CredentialKind.KEYRING_REF:
        ref = profile.metadata.get("ref")
        if not isinstance(ref, str):
            return CredentialStatus(status="rejected", detail="keyring reference missing")
        try:
            get_cached_credential(ref, env=env)
        except CredentialStorageError as exc:
            return CredentialStatus(status="rejected", detail=sanitize_credential_error(exc))
        return CredentialStatus(status="ok")
    if profile.kind is CredentialKind.API_KEY and env is not None:
        env_var = profile.metadata.get("env_var")
        if not isinstance(env_var, str) or not env_var:
            return CredentialStatus(status="unknown", detail="no environment variable configured")
        return CredentialStatus(status="ok") if env.get(env_var) else CredentialStatus(
            status="rejected",
            detail="secret reference could not resolve",
        )
    try:
        return source_for_auth_profile(profile).status()
    except (RuntimeError, ValueError) as exc:
        return CredentialStatus(status="rejected", detail=sanitize_credential_error(exc))


def auth_status_rows(
    profiles: list[AuthProfile],
    *,
    validate: bool = True,
    env: dict[str, str] | None = None,
) -> list[AuthStatusRow]:
    """Return redacted auth status rows, optionally resolving credential health."""
    rows: list[AuthStatusRow] = []
    for profile in profiles:
        status = (
            profile_runtime_status(profile, env=env)
            if validate
            else CredentialStatus(status=profile.last_status)
        )
        rows.append(
            AuthStatusRow(
                id=profile.id,
                provider_family=profile.provider_family,
                kind=profile.kind,
                backend=_profile_backend(profile),
                last_validated_at=_last_validated_at(profile),
                health_status=status.status,
                detail=status.detail,
                warning=_profile_warning(profile),
            )
        )
    return rows


def auth_status_payload(env: dict[str, str] | None = None) -> list[dict[str, object]]:
    """Return visible auth status rows from local state."""
    store = AuthProfileStore.from_env(env)
    profiles = visible_auth_profiles(store.list(), active_operator_session_from_env(env))
    return [row.as_dict() for row in auth_status_rows(profiles, env=env)]


def logout_provider(
    provider: str,
    *,
    profile_id: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Remove a provider profile and any cached keyring credential."""
    defaults = guided_provider_defaults(provider)
    target = profile_id or str(defaults["profile_id"])
    store = AuthProfileStore.from_env(env)
    removed_keyring_ref = False
    try:
        profile = store.get(target)
    except AuthProfileStoreError:
        profile = None
    if profile is not None and profile.kind is CredentialKind.KEYRING_REF:
        ref = profile.metadata.get("ref")
        if isinstance(ref, str):
            delete_cached_credential(ref, env=env)
            removed_keyring_ref = True
    store.delete(target)
    return {
        "provider": provider,
        "profile_id": target,
        "removed_profile": profile is not None,
        "removed_keyring_ref": removed_keyring_ref,
        "redacted": True,
    }


def migrate_env_profiles(
    *,
    dry_run: bool = True,
    consent: ConfirmPrompt | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Copy env-var profile credentials into cached keyring refs with consent."""
    values = os.environ if env is None else env
    store = AuthProfileStore.from_env(env)
    migrated: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for profile in store.list():
        if profile.kind is not CredentialKind.API_KEY:
            skipped.append({"profile_id": profile.id, "reason": "not-env-var-profile"})
            continue
        env_var = profile.metadata.get("env_var")
        if not isinstance(env_var, str) or not env_var:
            skipped.append({"profile_id": profile.id, "reason": "missing-env-var-reference"})
            continue
        value = values.get(env_var)
        if not value:
            skipped.append(
                {"profile_id": profile.id, "env_var": env_var, "reason": "env-var-unset"}
            )
            continue
        prompt = f"Migrate {profile.id} from {env_var} into cached credential storage?"
        if consent is not None and not consent(prompt):
            skipped.append({"profile_id": profile.id, "env_var": env_var, "reason": "declined"})
            continue
        updated = _profile_as_keyring(profile)
        if not dry_run:
            storage = put_cached_credential(_credential_ref(updated), value, env=env)
            metadata = dict(updated.metadata)
            metadata["credential_backend"] = storage.backend
            metadata["last_validated_at"] = datetime.now(UTC).isoformat()
            updated = updated.model_copy(update={"metadata": metadata, "last_status": "ok"})
            store.put(updated)
        migrated.append(
            {
                "profile_id": profile.id,
                "env_var": env_var,
                "new_kind": CredentialKind.KEYRING_REF,
                "dry_run": dry_run,
                "redacted": True,
            }
        )
    return {
        "dry_run": dry_run,
        "migrated": migrated,
        "skipped": skipped,
        "credential_storage": credential_storage_status(env).as_dict(),
        "redacted": True,
    }


def _build_keyring_profile(
    provider: str,
    *,
    defaults: dict[str, Any],
    profile_id: str | None,
    base_url: str | None,
    allow_local_base_url: bool,
) -> AuthProfile:
    profile = build_guided_auth_profile(
        defaults,
        profile_id=profile_id,
        env_var=str(defaults["env_var"]),
        secret_ref=None,
        ref_manager=DEFAULT_REF_MANAGER,
        secrets_root=None,
        base_url=base_url,
        allow_local_base_url=allow_local_base_url,
    )
    metadata = dict(profile.metadata)
    metadata.pop("env_var", None)
    metadata["ref"] = f"{profile.id}:api-key"
    metadata["source"] = "capture-and-cache"
    metadata["provider"] = provider
    return AuthProfile(
        id=profile.id,
        kind=CredentialKind.KEYRING_REF,
        provider_family=cast(ProviderFamily, profile.provider_family),
        metadata=metadata,
        created_at=datetime.now(UTC),
    )


def _profile_as_keyring(profile: AuthProfile) -> AuthProfile:
    metadata = dict(profile.metadata)
    metadata.pop("env_var", None)
    metadata["ref"] = f"{profile.id}:api-key"
    metadata["source"] = "capture-and-cache"
    return profile.model_copy(update={"kind": CredentialKind.KEYRING_REF, "metadata": metadata})


def _credential_ref(profile: AuthProfile) -> str:
    ref = profile.metadata.get("ref")
    if not isinstance(ref, str) or not ref:
        raise ValueError("keyring-ref auth profile requires metadata.ref")
    return ref


def _profile_backend(profile: AuthProfile) -> str | None:
    backend = profile.metadata.get("credential_backend")
    return backend if isinstance(backend, str) else None


def _profile_warning(profile: AuthProfile) -> str | None:
    if _profile_backend(profile) == "file":
        return FILE_BACKED_CREDENTIAL_WARNING
    return None


def _last_validated_at(profile: AuthProfile) -> str | None:
    value = profile.metadata.get("last_validated_at")
    return value if isinstance(value, str) else None


__all__ = [
    "AuthCaptureResult",
    "AuthStatusRow",
    "auth_status_rows",
    "auth_status_payload",
    "capture_and_cache_login",
    "explicit_reference_login",
    "health_check_profile_secret",
    "logout_provider",
    "migrate_env_profiles",
    "profile_runtime_status",
]
