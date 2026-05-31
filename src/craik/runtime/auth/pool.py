"""File-backed credential pool selection and health tracking."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel
from craik.runtime.auth.profile import AuthProfile
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.paths import ensure_craik_home, resolve_craik_home
from craik.runtime.providers.provider_transport import ProviderFamily

CREDENTIAL_POOL_FILENAME = "credential_pool.json"
CREDENTIAL_POOL_SCHEMA_VERSION = 1
OWNER_ONLY_FILE_MODE = 0o600

# Legacy provider-family identifier rewritten to its canonical form on load so a
# stored ``gemini:default`` pool resolves as ``google:default`` (gemini→google
# rename). Mirrors the AuthProfileStore on-load migration.
_LEGACY_FAMILY = "gemini"
_CANONICAL_FAMILY = "google"


def _canonical_pool_token(value: str) -> str:
    prefix = f"{_LEGACY_FAMILY}:"
    if value.startswith(prefix):
        return f"{_CANONICAL_FAMILY}:{value[len(prefix):]}"
    return value


PoolStrategy = Literal["round_robin", "failover", "weighted"]
PoolOutcome = Literal["success", "failed", "rejected", "rate_limited"]


class CredentialPoolError(RuntimeError):
    """Raised when credential pool state or selection fails."""


class CredentialPoolEntry(CraikModel):
    """One profile entry inside a credential pool."""

    profile_id: str
    weight: int = Field(default=1, ge=1)
    consecutive_failures: int = Field(default=0, ge=0)
    backoff_until: datetime | None = None
    last_outcome: PoolOutcome | None = None


class CredentialPoolConfig(CraikModel):
    """Configured pool for one provider family and purpose."""

    id: str
    provider_family: ProviderFamily
    purpose: str = "default"
    strategy: PoolStrategy = "round_robin"
    profiles: list[CredentialPoolEntry] = Field(min_length=1)
    cursor: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_pool(self) -> CredentialPoolConfig:
        if not self.id:
            raise ValueError("credential pool id is required")
        if len({entry.profile_id for entry in self.profiles}) != len(self.profiles):
            raise ValueError("credential pool profile ids must be unique")
        return self


class CredentialPool:
    """Select auth profiles from file-backed credential pools."""

    def __init__(self, home: Path, profile_store: AuthProfileStore | None = None) -> None:
        self.home = home.expanduser().resolve()
        self.path = self.home / CREDENTIAL_POOL_FILENAME
        self.lock_path = self.home / f"{CREDENTIAL_POOL_FILENAME}.lock"
        self.profile_store = profile_store or AuthProfileStore(self.home)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> CredentialPool:
        ensure_craik_home(env)
        home = resolve_craik_home(env)
        return cls(home, AuthProfileStore(home))

    def put(self, config: CredentialPoolConfig) -> None:
        """Create or replace a credential pool."""
        with self._locked():
            pools = self._read_unlocked()
            pools[config.id] = config
            self._write_unlocked(pools)

    def get(self, pool_id: str) -> CredentialPoolConfig:
        """Return one credential pool, resolving legacy gemini ids."""
        with self._locked():
            pools = self._read_unlocked()
            try:
                return pools[pool_id]
            except KeyError:
                pass
            canonical = _canonical_pool_token(pool_id)
            try:
                return pools[canonical]
            except KeyError as exc:
                raise CredentialPoolError(f"credential pool not found: {pool_id}") from exc

    def select(self, family: ProviderFamily, *, purpose: str = "default") -> AuthProfile:
        """Select the next healthy profile for a family and purpose."""
        with self._locked():
            pools = self._read_unlocked()
            pool = _pool_for(pools, family=family, purpose=purpose)
            return self._select_from_pool_unlocked(pools, pool)

    def select_from_pool(self, pool_id: str) -> AuthProfile:
        """Select the next healthy profile from a specific pool."""
        with self._locked():
            pools = self._read_unlocked()
            try:
                pool = pools[pool_id]
            except KeyError as exc:
                raise CredentialPoolError(f"credential pool not found: {pool_id}") from exc
            return self._select_from_pool_unlocked(pools, pool)

    def _select_from_pool_unlocked(
        self,
        pools: dict[str, CredentialPoolConfig],
        pool: CredentialPoolConfig,
    ) -> AuthProfile:
        entry, updated = _select_entry(pool)
        pools[updated.id] = updated
        self._write_unlocked(pools)
        return self.profile_store.get(entry.profile_id)

    def report(self, profile_id: str, outcome: PoolOutcome) -> None:
        """Record a credential selection outcome and update health."""
        with self._locked():
            pools = self._read_unlocked()
            changed = False
            for pool in list(pools.values()):
                entries: list[CredentialPoolEntry] = []
                for entry in pool.profiles:
                    if entry.profile_id != profile_id:
                        entries.append(entry)
                        continue
                    entries.append(_reported_entry(entry, outcome))
                    changed = True
                if changed:
                    pools[pool.id] = pool.model_copy(update={"profiles": entries})
            if changed:
                self._write_unlocked(pools)

    def _read_unlocked(self) -> dict[str, CredentialPoolConfig]:
        if not self.path.exists():
            return {}
        parsed = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict) or parsed.get("version") != CREDENTIAL_POOL_SCHEMA_VERSION:
            raise CredentialPoolError("credential pool store has unsupported schema version")
        raw_pools = parsed.get("pools", [])
        if not isinstance(raw_pools, list):
            raise CredentialPoolError("credential pool store pools must be a list")
        pools: dict[str, CredentialPoolConfig] = {}
        for item in raw_pools:
            pool = CredentialPoolConfig.model_validate(item)
            pools[pool.id] = pool
        migrated, changed = _migrate_legacy_pools(pools)
        if changed:
            # One-time on-load migration to the canonical google family.
            self._write_unlocked(migrated)
        return migrated

    def _write_unlocked(self, pools: dict[str, CredentialPoolConfig]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CREDENTIAL_POOL_SCHEMA_VERSION,
            "pools": [
                pool.model_dump(mode="json")
                for pool in sorted(pools.values(), key=lambda item: item.id)
            ],
        }
        fd, temp_name = tempfile.mkstemp(
            prefix=".credential-pool.",
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


def _migrate_legacy_pools(
    pools: dict[str, CredentialPoolConfig],
) -> tuple[dict[str, CredentialPoolConfig], bool]:
    """Rewrite legacy gemini pool identities to google in place."""
    changed = False
    migrated: dict[str, CredentialPoolConfig] = {}
    for pool in pools.values():
        new_pool, pool_changed = _migrate_legacy_pool(pool)
        changed = changed or pool_changed
        migrated[new_pool.id] = new_pool
    return migrated, changed


def _migrate_legacy_pool(pool: CredentialPoolConfig) -> tuple[CredentialPoolConfig, bool]:
    update: dict[str, object] = {}
    canonical_id = _canonical_pool_token(pool.id)
    if canonical_id != pool.id:
        update["id"] = canonical_id
    if pool.provider_family == _LEGACY_FAMILY:
        update["provider_family"] = _CANONICAL_FAMILY
    entries = [
        entry.model_copy(update={"profile_id": _canonical_pool_token(entry.profile_id)})
        if _canonical_pool_token(entry.profile_id) != entry.profile_id
        else entry
        for entry in pool.profiles
    ]
    if any(new is not old for new, old in zip(entries, pool.profiles, strict=True)):
        update["profiles"] = entries
    if not update:
        return pool, False
    return pool.model_copy(update=update), True


def _pool_for(
    pools: dict[str, CredentialPoolConfig],
    *,
    family: ProviderFamily,
    purpose: str,
) -> CredentialPoolConfig:
    for pool in pools.values():
        if pool.provider_family == family and pool.purpose == purpose:
            return pool
    raise CredentialPoolError(f"credential pool not found for {family}:{purpose}")


def _select_entry(pool: CredentialPoolConfig) -> tuple[CredentialPoolEntry, CredentialPoolConfig]:
    healthy = [entry for entry in pool.profiles if _healthy(entry)]
    if not healthy:
        raise CredentialPoolError(f"credential pool {pool.id} has no healthy profiles")
    if pool.strategy == "failover":
        return healthy[0], pool
    weighted = _weighted_entries(healthy if pool.strategy == "weighted" else pool.profiles)
    weighted = [entry for entry in weighted if _healthy(entry)]
    if not weighted:
        raise CredentialPoolError(f"credential pool {pool.id} has no healthy profiles")
    index = pool.cursor % len(weighted)
    selected = weighted[index]
    updated = pool.model_copy(update={"cursor": pool.cursor + 1})
    return selected, updated


def _weighted_entries(entries: list[CredentialPoolEntry]) -> list[CredentialPoolEntry]:
    weighted: list[CredentialPoolEntry] = []
    for entry in entries:
        weighted.extend([entry] * entry.weight)
    return weighted


def _healthy(entry: CredentialPoolEntry) -> bool:
    return entry.backoff_until is None or entry.backoff_until <= datetime.now(UTC)


def _reported_entry(entry: CredentialPoolEntry, outcome: PoolOutcome) -> CredentialPoolEntry:
    if outcome == "success":
        return entry.model_copy(
            update={
                "consecutive_failures": 0,
                "backoff_until": None,
                "last_outcome": outcome,
            }
        )
    failures = entry.consecutive_failures + 1
    backoff_seconds = min(300, 2**failures)
    return entry.model_copy(
        update={
            "consecutive_failures": failures,
            "backoff_until": datetime.now(UTC) + timedelta(seconds=backoff_seconds),
            "last_outcome": outcome,
        }
    )
