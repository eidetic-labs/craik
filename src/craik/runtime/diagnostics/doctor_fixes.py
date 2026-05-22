"""Explicit fix actions for `craik doctor --fix`."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from ipaddress import ip_address

from craik.runtime.auth.store import AUTH_PROFILES_FILENAME, OWNER_ONLY_FILE_MODE
from craik.runtime.paths import CraikPaths
from craik.runtime.store import DATABASE_NAME, LocalStore


@dataclass(frozen=True)
class DoctorFix:
    """One explicit doctor repair action."""

    name: str
    status: str
    summary: str
    unsafe: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "unsafe": self.unsafe,
        }


def doctor_fixes(
    paths: CraikPaths,
    *,
    dry_run: bool,
    confirm_unsafe: bool,
) -> list[DoctorFix]:
    fixes = [
        *_local_state_fixes(paths, dry_run=dry_run),
        *_permission_fixes(paths, dry_run=dry_run),
        *_public_bind_fixes(paths, dry_run=dry_run, confirm_unsafe=confirm_unsafe),
    ]
    if not fixes:
        return [
            DoctorFix(
                name="no_fixes",
                status="skipped",
                summary="No supported automatic fixes were needed.",
            )
        ]
    return fixes


def _local_state_fixes(paths: CraikPaths, *, dry_run: bool) -> list[DoctorFix]:
    fixes: list[DoctorFix] = []
    if not paths.home.exists():
        if not dry_run:
            paths.home.mkdir(parents=True, exist_ok=True)
            paths.config.mkdir(parents=True, exist_ok=True)
            paths.state.mkdir(parents=True, exist_ok=True)
        fixes.append(
            DoctorFix(
                name="create_home",
                status="planned" if dry_run else "applied",
                summary=f"Create Craik home directories at {paths.home}.",
            )
        )
    if not (paths.state / DATABASE_NAME).exists():
        if not dry_run:
            store = LocalStore.from_paths(paths)
            try:
                store.initialize()
            finally:
                store.close()
        fixes.append(
            DoctorFix(
                name="initialize_store",
                status="planned" if dry_run else "applied",
                summary="Initialize the local store database.",
            )
        )
    return fixes


def _permission_fixes(paths: CraikPaths, *, dry_run: bool) -> list[DoctorFix]:
    if os.name != "posix":
        return []
    path = paths.home / AUTH_PROFILES_FILENAME
    if not path.exists():
        return []
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode <= OWNER_ONLY_FILE_MODE:
        return []
    if not dry_run:
        path.chmod(OWNER_ONLY_FILE_MODE)
    return [
        DoctorFix(
            name="chmod_auth_profiles",
            status="planned" if dry_run else "applied",
            summary="Set auth-profiles.json to owner-only permissions.",
        )
    ]


def _public_bind_fixes(
    paths: CraikPaths,
    *,
    dry_run: bool,
    confirm_unsafe: bool,
) -> list[DoctorFix]:
    store = _open_existing_store(paths)
    if store is None:
        return []
    try:
        public_configs = [
            config
            for config in store.list_gateway_configs()
            if _is_public_bind(config.bind_host)
        ]
        if not public_configs:
            return []
        if not confirm_unsafe:
            return [
                DoctorFix(
                    name="rebind_public_gateway",
                    status="requires_confirmation",
                    summary="Would rebind public gateway configs to 127.0.0.1.",
                    unsafe=True,
                )
            ]
        if not dry_run:
            for config in public_configs:
                store.put_gateway_config(config.model_copy(update={"bind_host": "127.0.0.1"}))
        return [
            DoctorFix(
                name="rebind_public_gateway",
                status="planned" if dry_run else "applied",
                summary="Rebind public gateway configs to 127.0.0.1.",
                unsafe=True,
            )
        ]
    finally:
        store.close()


def _open_existing_store(paths: CraikPaths) -> LocalStore | None:
    database_path = paths.state / DATABASE_NAME
    if not database_path.exists():
        return None
    return LocalStore(database_path)


def _is_public_bind(host: str) -> bool:
    try:
        return ip_address(host).is_unspecified
    except ValueError:
        return False
