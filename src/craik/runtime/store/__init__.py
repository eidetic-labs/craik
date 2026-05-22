"""SQLite-backed local runtime store."""

# ruff: noqa: F401,I001

from __future__ import annotations

from .base import (
    CONTRACT_KINDS,
    CURRENT_MIGRATION,
    DATABASE_NAME,
    MIGRATION_RECOVERY_GUIDANCE,
    LocalStoreCore,
    LocalStoreCorruptError,
    LocalStoreError,
    LocalStoreMigrationError,
    UnknownContractError,
    UnredactedSecretError,
)
from .extensions import ExtensionStoreMixin
from .gateway import GatewayStoreMixin
from .memory import MemoryStoreMixin
from .profiles import ProfileStoreMixin
from .work import WorkStoreMixin


class LocalStore(
    MemoryStoreMixin,
    WorkStoreMixin,
    ExtensionStoreMixin,
    GatewayStoreMixin,
    ProfileStoreMixin,
):
    """SQLite persistence for v0.1 runtime state."""


__all__ = [
    "CURRENT_MIGRATION",
    "CONTRACT_KINDS",
    "DATABASE_NAME",
    "MIGRATION_RECOVERY_GUIDANCE",
    "LocalStore",
    "LocalStoreCorruptError",
    "LocalStoreError",
    "LocalStoreMigrationError",
    "UnknownContractError",
    "UnredactedSecretError",
]
