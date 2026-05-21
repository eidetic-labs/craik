"""Forward-only local-store migration registry."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from craik.contracts.registry import CONTRACT_REGISTRY

CURRENT_MIGRATION = 4
MIGRATION_RECOVERY_GUIDANCE = (
    "Back up state/craik.sqlite3, keep the original file unchanged, and run "
    "`craik doctor` for diagnostics. If the database version is newer than this "
    "Craik build supports, upgrade Craik before opening the store. If a migration "
    "failed partway through, restore the backup or copy the database aside before retrying."
)

MigrationCallable = Callable[[sqlite3.Connection], None]


class StoreMigrationRuntimeError(RuntimeError):
    """Raised when a registered local-store migration cannot complete."""


@dataclass(frozen=True)
class StoreMigration:
    """One forward-only local-store migration step."""

    version: int
    name: str
    apply: MigrationCallable


class StoreMigrationRunner:
    """Apply registered local-store migrations in version order."""

    def __init__(self, migrations: list[StoreMigration]) -> None:
        self.migrations = _ordered_migrations(migrations)
        self.current_version = self.migrations[-1].version if self.migrations else 0

    def apply(self, connection: sqlite3.Connection) -> None:
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current > self.current_version:
            raise StoreMigrationRuntimeError(
                f"local store migration {current} is newer than supported {self.current_version}"
            )
        for migration in self.migrations:
            if current >= migration.version:
                continue
            migration.apply(connection)
            current = migration.version
        if current != self.current_version:
            raise StoreMigrationRuntimeError(
                f"local store migration ended at {current}, expected {self.current_version}"
            )


def apply_local_store_migrations(connection: sqlite3.Connection) -> None:
    """Apply all registered local-store migrations."""
    LOCAL_STORE_MIGRATIONS.apply(connection)


def _ordered_migrations(migrations: list[StoreMigration]) -> list[StoreMigration]:
    ordered = sorted(migrations, key=lambda migration: migration.version)
    expected = list(range(1, len(ordered) + 1))
    actual = [migration.version for migration in ordered]
    if actual != expected:
        raise ValueError(f"local-store migrations must be contiguous from 1: {actual}")
    return ordered


def _migration_1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS records (
          kind TEXT NOT NULL,
          id TEXT NOT NULL,
          schema TEXT NOT NULL,
          version TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (kind, id)
        );
        CREATE INDEX IF NOT EXISTS idx_records_schema ON records(schema);
        CREATE TABLE IF NOT EXISTS migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );
        """
    )
    _record_migration(connection, 1)


def _migration_2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS local_store_metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_records_kind_updated_at
          ON records(kind, updated_at);
        """
    )
    _write_metadata(
        connection,
        {
            "schema_version": str(CURRENT_MIGRATION),
            "contract_registry_count": str(len(CONTRACT_REGISTRY)),
        },
    )
    _record_migration(connection, 2)


def _migration_3(connection: sqlite3.Connection) -> None:
    _write_metadata(
        connection,
        {
            "migration_framework": "registered",
            "schema_version": str(CURRENT_MIGRATION),
        },
    )
    _record_migration(connection, 3)


def _migration_4(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS instruction_sources (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          path TEXT NOT NULL,
          owner TEXT NOT NULL,
          trust_boundary TEXT NOT NULL,
          active INTEGER NOT NULL,
          registered_by TEXT NOT NULL,
          registered_at TEXT NOT NULL,
          content_hash TEXT,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_instruction_sources_project
          ON instruction_sources(project_id, kind, path);
        """
    )
    _write_metadata(
        connection,
        {
            "instruction_sources_table": "registered",
            "schema_version": str(CURRENT_MIGRATION),
        },
    )
    _record_migration(connection, 4)


def _write_metadata(connection: sqlite3.Connection, metadata: dict[str, str]) -> None:
    now = _utc_now()
    for key, value in metadata.items():
        connection.execute(
            """
            INSERT INTO local_store_metadata(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value,
              updated_at = excluded.updated_at
            """,
            (key, value, now),
        )


def _record_migration(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO migrations(version, applied_at) VALUES (?, ?)",
        (version, _utc_now()),
    )
    connection.execute(f"PRAGMA user_version = {version}")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


LOCAL_STORE_MIGRATIONS = StoreMigrationRunner(
    [
        StoreMigration(1, "initial_records", _migration_1),
        StoreMigration(2, "local_store_metadata", _migration_2),
        StoreMigration(3, "migration_framework_metadata", _migration_3),
        StoreMigration(4, "instruction_sources_table", _migration_4),
    ]
)


__all__ = [
    "CURRENT_MIGRATION",
    "LOCAL_STORE_MIGRATIONS",
    "MIGRATION_RECOVERY_GUIDANCE",
    "StoreMigration",
    "StoreMigrationRunner",
    "StoreMigrationRuntimeError",
    "apply_local_store_migrations",
]
