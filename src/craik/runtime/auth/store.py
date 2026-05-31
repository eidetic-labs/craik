"""File-backed auth profile store."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from craik.contracts.models import CapabilityReceipt, ReceiptResult
from craik.runtime.auth.profile import AuthProfile, CredentialHealthStatus
from craik.runtime.paths import ensure_craik_home, resolve_craik_home

AUTH_PROFILES_FILENAME = "auth-profiles.json"
AUTH_PROFILES_SCHEMA_VERSION = 1
OWNER_ONLY_FILE_MODE = 0o600

# Legacy provider-family token rewritten to its canonical form on load
# (gemini→google rename). Persisted profile ids, families, and provider
# metadata tokens are migrated in place and written back one time.
_LEGACY_FAMILY_TOKEN = "gemini"
_CANONICAL_FAMILY_TOKEN = "google"


def _canonical_profile_id(profile_id: str) -> str:
    """Rewrite a legacy ``gemini:*`` profile id to the canonical ``google:*``."""
    prefix = f"{_LEGACY_FAMILY_TOKEN}:"
    if profile_id.startswith(prefix):
        return f"{_CANONICAL_FAMILY_TOKEN}:{profile_id[len(prefix):]}"
    return profile_id


class AuthProfileStoreError(RuntimeError):
    """Raised when auth profile state cannot be loaded or written."""


class AuthProfileNotFoundError(AuthProfileStoreError):
    """Raised when a requested auth profile does not exist."""


class AuthProfileStore:
    """Read and write auth profiles in a local Craik home directory."""

    def __init__(self, home: Path) -> None:
        self.home = home.expanduser().resolve()
        self.path = self.home / AUTH_PROFILES_FILENAME
        self.lock_path = self.home / f"{AUTH_PROFILES_FILENAME}.lock"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AuthProfileStore:
        """Create a store from CRAIK_HOME, ensuring the home layout exists."""
        ensure_craik_home(env)
        return cls(resolve_craik_home(env))

    def list(self) -> list[AuthProfile]:
        """Return all configured auth profiles."""
        with self._locked():
            return sorted(self._read_unlocked().values(), key=lambda profile: profile.id)

    def get(self, profile_id: str) -> AuthProfile:
        """Return one auth profile by id, resolving legacy gemini ids."""
        with self._locked():
            profiles = self._read_unlocked()
            try:
                return profiles[profile_id]
            except KeyError:
                pass
            canonical = _canonical_profile_id(profile_id)
            try:
                return profiles[canonical]
            except KeyError as exc:
                raise AuthProfileNotFoundError(f"auth profile not found: {profile_id}") from exc

    def put(self, profile: AuthProfile) -> None:
        """Create or replace one auth profile."""
        with self._locked():
            profiles = self._read_unlocked()
            profiles[profile.id] = profile
            self._write_unlocked(profiles)

    def delete(self, profile_id: str) -> None:
        """Delete one auth profile if present."""
        with self._locked():
            profiles = self._read_unlocked()
            profiles.pop(profile_id, None)
            self._write_unlocked(profiles)

    def mark_used(self, profile_id: str, status: CredentialHealthStatus) -> AuthProfile:
        """Record profile use and return the updated profile."""
        with self._locked():
            profiles = self._read_unlocked()
            try:
                current = profiles[profile_id]
            except KeyError as exc:
                raise AuthProfileNotFoundError(f"auth profile not found: {profile_id}") from exc
            updated = current.model_copy(
                update={
                    "last_used_at": datetime.now(UTC),
                    "last_status": status,
                }
            )
            profiles[profile_id] = updated
            self._write_unlocked(profiles)
            return updated

    def approve(
        self,
        profile_id: str,
        *,
        run_id: str,
        approved_by: str,
        approved_at: datetime | None = None,
    ) -> AuthProfile:
        """Record an approval marker for a credential profile."""
        with self._locked():
            profiles = self._read_unlocked()
            try:
                current = profiles[profile_id]
            except KeyError as exc:
                raise AuthProfileNotFoundError(f"auth profile not found: {profile_id}") from exc
            metadata = dict(current.metadata)
            metadata["approval"] = {
                "run_id": run_id,
                "approved_by": approved_by,
                "approved_at": (approved_at or datetime.now(UTC)).isoformat(),
            }
            updated = current.model_copy(update={"metadata": metadata})
            profiles[profile_id] = updated
            self._write_unlocked(profiles)
            return updated

    def grant_authorization(
        self,
        profile_id: str,
        *,
        to_subject: str | None = None,
        to_group: str | None = None,
        granted_by: str,
        granted_at: datetime | None = None,
    ) -> AuthProfile:
        """Authorize one operator subject or group to use a credential profile."""
        if not to_subject and not to_group:
            raise AuthProfileStoreError("authorization grant requires a subject or group")
        granted_at = granted_at or datetime.now(UTC)
        with self._locked():
            profiles = self._read_unlocked()
            try:
                current = profiles[profile_id]
            except KeyError as exc:
                raise AuthProfileNotFoundError(f"auth profile not found: {profile_id}") from exc
            subjects = _append_unique(current.authorized_operators, to_subject)
            groups = _append_unique(current.authorized_operator_groups, to_group)
            receipt = _authorization_receipt(
                profile_id=profile_id,
                to_subject=to_subject,
                to_group=to_group,
                granted_by=granted_by,
                granted_at=granted_at,
            )
            updated = current.model_copy(
                update={
                    "authorized_operators": subjects,
                    "authorized_operator_groups": groups,
                    "authorization_provenance": [
                        *current.authorization_provenance,
                        receipt,
                    ],
                }
            )
            profiles[profile_id] = updated
            self._write_unlocked(profiles)
            return updated

    def _read_unlocked(self) -> dict[str, AuthProfile]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AuthProfileStoreError("auth profile store contains invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("version") != AUTH_PROFILES_SCHEMA_VERSION:
            raise AuthProfileStoreError("auth profile store has unsupported schema version")
        raw_profiles = payload.get("profiles", [])
        if not isinstance(raw_profiles, list):
            raise AuthProfileStoreError("auth profile store profiles must be a list")
        profiles: dict[str, AuthProfile] = {}
        try:
            for item in raw_profiles:
                profile = AuthProfile.model_validate(item)
                profiles[profile.id] = profile
        except ValidationError as exc:
            raise AuthProfileStoreError("auth profile store contains invalid profile data") from exc
        migrated, changed = _migrate_legacy_profiles(profiles)
        if changed:
            # One-time on-load migration: rewrite legacy gemini identities to
            # google and persist within the same lock so it never re-runs.
            self._write_unlocked(migrated)
        return migrated

    def _write_unlocked(self, profiles: dict[str, AuthProfile]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": AUTH_PROFILES_SCHEMA_VERSION,
            "profiles": [
                profile.model_dump(mode="json")
                for profile in sorted(profiles.values(), key=lambda item: item.id)
            ],
        }
        fd, temp_name = tempfile.mkstemp(
            prefix=".auth-profiles.",
            suffix=".tmp",
            dir=self.home,
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            if os.name == "posix":
                temp_path.chmod(OWNER_ONLY_FILE_MODE)
            os.replace(temp_path, self.path)
            if os.name == "posix":
                self.path.chmod(OWNER_ONLY_FILE_MODE)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.home.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            import fcntl

            with self.lock_path.open("a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
            return

        lock_fd: int | None = None
        while lock_fd is None:
            try:
                lock_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                time.sleep(0.01)
        try:
            yield
        finally:
            os.close(lock_fd)
            self.lock_path.unlink(missing_ok=True)


def _migrate_legacy_profiles(
    profiles: dict[str, AuthProfile],
) -> tuple[dict[str, AuthProfile], bool]:
    """Rewrite legacy gemini profile identities to google in place.

    Returns the (possibly rewritten) profile map keyed by canonical id and a
    flag indicating whether any profile was changed. Only the profile-level
    identity is migrated: id prefix, ``provider_family``, and the ``provider``
    token in ``metadata``. Signed ``authorization_provenance`` receipts are left
    byte-for-byte intact so their ``self_hash`` stays valid.
    """
    changed = False
    migrated: dict[str, AuthProfile] = {}
    for profile in profiles.values():
        new_profile, profile_changed = _migrate_legacy_profile(profile)
        changed = changed or profile_changed
        migrated[new_profile.id] = new_profile
    return migrated, changed


def _migrate_legacy_profile(profile: AuthProfile) -> tuple[AuthProfile, bool]:
    update: dict[str, object] = {}
    canonical_id = _canonical_profile_id(profile.id)
    if canonical_id != profile.id:
        update["id"] = canonical_id
    if profile.provider_family == _LEGACY_FAMILY_TOKEN:
        update["provider_family"] = _CANONICAL_FAMILY_TOKEN
    if profile.metadata.get("provider") == _LEGACY_FAMILY_TOKEN:
        metadata = dict(profile.metadata)
        metadata["provider"] = _CANONICAL_FAMILY_TOKEN
        update["metadata"] = metadata
    if not update:
        return profile, False
    return profile.model_copy(update=update), True


def _append_unique(existing: list[str] | None, value: str | None) -> list[str] | None:
    if value is None:
        return existing
    values = list(existing or [])
    if value not in values:
        values.append(value)
    return values


def _authorization_receipt(
    *,
    profile_id: str,
    to_subject: str | None,
    to_group: str | None,
    granted_by: str,
    granted_at: datetime,
) -> CapabilityReceipt:
    target = to_subject or to_group or "unknown"
    return CapabilityReceipt(
        id=f"receipt_credential_authorization_{profile_id.replace(':', '_')}_{target}",
        task_id="auth_profile_authorization",
        actor=granted_by,
        capability="credential.authorize",
        target=profile_id,
        policy_profile="strict",
        fail_open=False,
        reason="Credential profile authorization granted.",
        result=ReceiptResult(
            status="passed",
            summary="Credential profile authorization granted.",
            metadata={
                "auth_profile_id": profile_id,
                "authorized_operator": to_subject,
                "authorized_operator_group": to_group,
            },
        ),
        redacted=True,
        created_at=granted_at,
    )


def auth_profile_store_owner_only(path: Path) -> bool:
    """Return whether an auth profile store file is owner-readable/writable only."""
    if os.name != "posix":
        return True
    mode = stat.S_IMODE(path.stat().st_mode)
    return mode == OWNER_ONLY_FILE_MODE
