"""SQLite-backed local runtime store."""

from __future__ import annotations

# ruff: noqa: F401
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ValidationError

from craik.contracts.models import (
    AdapterPackage,
    AdjudicationOutcome,
    AgentMessage,
    Assumption,
    CapabilityGrant,
    CapabilityReceipt,
    CaseFile,
    CompiledPrompt,
    ContextDebtRecord,
    ContextRequest,
    ContradictionReport,
    DebateSummary,
    DebateTurn,
    DistilledInstructionProposal,
    EvidenceCoverageScore,
    EvidenceReference,
    ExitDisciplineCheck,
    GatewayConfig,
    GatewayRuntimeState,
    Handoff,
    HandoffQualityScore,
    HumanDelegationPoint,
    InstructionPromotionReview,
    InstructionProvenance,
    InstructionRegistryReceipt,
    InstructionSource,
    InstructionSourceRegistration,
    InstructionSourceRegistry,
    InstructionSourceSnapshot,
    IntentLock,
    KnowledgeFreshnessProbe,
    KnownTrap,
    MemoryDiff,
    MemoryImpactPreview,
    MemoryProposal,
    NegativeKnowledge,
    PluginCapabilityGrant,
    PluginDescriptor,
    PluginProbation,
    PluginReceipt,
    PolicyEnvelope,
    ProjectProfile,
    PromotedInstructionConstraint,
    RecoverySession,
    RedTeamFinding,
    ReferenceIntegration,
    ReviewRequest,
    ReviewResult,
    RunDelta,
    RunOutput,
    RuntimeCriticFinding,
    ScopeChangeRequest,
    ScopeChangeResult,
    ScratchpadRecord,
    SkillInvocationContext,
    SkillPackage,
    SkillRegistry,
    TaskRequest,
    TaskRun,
    ToolResultAttestation,
    UnknownRecord,
    WorkerResult,
    WorkGraphEvent,
)
from craik.contracts.registry import CONTRACT_REGISTRY, ContractModel
from craik.runtime.paths import CraikPaths, ensure_craik_home
from craik.runtime.policy.redaction import contains_unredacted_secret
from craik.runtime.store.migrations import (
    CURRENT_MIGRATION,
    MIGRATION_RECOVERY_GUIDANCE,
    StoreMigrationRuntimeError,
    _record_migration,
)
from craik.runtime.store.migrations import (
    apply_local_store_migrations as _apply_migrations,
)
from craik.runtime.store_kinds import CONTRACT_KINDS

DATABASE_NAME = "craik.sqlite3"

class LocalStoreError(RuntimeError):
    """Base error for local store failures."""


class LocalStoreCorruptError(LocalStoreError):
    """Raised when the SQLite database cannot be read as a Craik store."""


class LocalStoreMigrationError(LocalStoreCorruptError):
    """Raised when a local store migration cannot be applied safely."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{message} Recovery: {MIGRATION_RECOVERY_GUIDANCE}")


class UnredactedSecretError(LocalStoreError):
    """Raised when a payload appears to contain unredacted secret material."""


class UnknownContractError(LocalStoreError):
    """Raised when a contract is not part of the local store schema."""




class LocalStoreCore:
    """SQLite persistence for v0.1 runtime state."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def from_paths(cls, paths: CraikPaths) -> Self:
        """Open the default local store under a resolved Craik home."""
        return cls(paths.state / DATABASE_NAME)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Self:
        """Ensure Craik home exists and open its default local store."""
        return cls.from_paths(ensure_craik_home(env))

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._connection.close()

    def initialize(self) -> None:
        """Apply local store migrations."""
        try:
            with self._connection:
                connection = self._connection
                _apply_migrations(connection)
        except StoreMigrationRuntimeError as error:
            raise LocalStoreMigrationError(str(error)) from error
        except sqlite3.DatabaseError as error:
            message = f"cannot initialize local store: {error}"
            raise LocalStoreMigrationError(message) from error

    def migration_version(self) -> int:
        """Return the current local store migration version."""
        try:
            row = self._connection.execute("PRAGMA user_version").fetchone()
            return int(row[0])
        except sqlite3.DatabaseError as error:
            message = f"cannot read local store migration version: {error}"
            raise LocalStoreCorruptError(message) from error

    def applied_migrations(self) -> list[dict[str, str | int]]:
        """Return migration history recorded in the local store."""
        try:
            rows = self._connection.execute(
                "SELECT version, applied_at FROM migrations ORDER BY version"
            ).fetchall()
        except sqlite3.DatabaseError as error:
            message = f"cannot read local store migration history: {error}"
            raise LocalStoreCorruptError(message) from error
        return [
            {"version": int(row["version"]), "applied_at": str(row["applied_at"])}
            for row in rows
        ]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run statements in a commit-or-rollback transaction."""
        try:
            with self._connection:
                yield self._connection
        except sqlite3.DatabaseError as error:
            raise LocalStoreCorruptError(f"local store transaction failed: {error}") from error

    def put_contract(self, contract: BaseModel) -> None:
        """Persist a supported contract payload after validation."""
        payload = contract.model_dump(mode="json", by_alias=True)
        schema_name = str(payload.get("schema"))
        kind = _kind_for_schema(schema_name)
        model = CONTRACT_REGISTRY[schema_name]
        validated = model.model_validate(payload)
        payload = validated.model_dump(mode="json", by_alias=True)
        _reject_unredacted_secrets(payload)
        now = _utc_now()

        try:
            with self.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO records (
                      kind, id, schema, version, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(kind, id) DO UPDATE SET
                      schema = excluded.schema,
                      version = excluded.version,
                      payload_json = excluded.payload_json,
                      updated_at = excluded.updated_at
                    """,
                    (
                        kind,
                        payload["id"],
                        payload["schema"],
                        payload["version"],
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        now,
                        now,
                    ),
                )
        except sqlite3.DatabaseError as error:
            message = f"cannot persist contract {schema_name}: {error}"
            raise LocalStoreCorruptError(message) from error

    def get_contract(self, schema_name: str, contract_id: str) -> BaseModel | None:
        """Load and validate a contract by schema and id."""
        kind = _kind_for_schema(schema_name)
        model = CONTRACT_REGISTRY[schema_name]
        try:
            row = self._connection.execute(
                "SELECT payload_json FROM records WHERE kind = ? AND id = ?",
                (kind, contract_id),
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise LocalStoreCorruptError(f"cannot read contract {schema_name}: {error}") from error
        if row is None:
            return None
        return _parse_payload(model, str(row["payload_json"]))

    def list_contracts(self, schema_name: str) -> list[BaseModel]:
        """Load all contracts for a schema in stable id order."""
        kind = _kind_for_schema(schema_name)
        model = CONTRACT_REGISTRY[schema_name]
        try:
            rows = self._connection.execute(
                "SELECT payload_json FROM records WHERE kind = ? ORDER BY id",
                (kind,),
            ).fetchall()
        except sqlite3.DatabaseError as error:
            raise LocalStoreCorruptError(f"cannot list contracts {schema_name}: {error}") from error
        return [_parse_payload(model, str(row["payload_json"])) for row in rows]
def _parse_payload(model: ContractModel, payload_json: str) -> BaseModel:
    try:
        return model.model_validate_json(payload_json)
    except ValidationError as error:
        raise LocalStoreCorruptError(f"stored payload failed validation: {error}") from error


def _kind_for_schema(schema_name: str) -> str:
    try:
        return CONTRACT_KINDS[schema_name]
    except KeyError:
        message = f"unsupported local store contract schema: {schema_name}"
        raise UnknownContractError(message) from None


def _reject_unredacted_secrets(value: Any) -> None:
    if contains_unredacted_secret(value):
        raise UnredactedSecretError("refusing to persist unredacted secret material")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _cast_optional[T: BaseModel](model: type[T], value: BaseModel | None) -> T | None:
    if value is None:
        return None
    if not isinstance(value, model):
        raise TypeError(f"expected {model.__name__}, got {type(value).__name__}")
    return value


def _cast_list[T: BaseModel](model: type[T], values: list[BaseModel]) -> list[T]:
    return [_cast_required(model, value) for value in values]


def _cast_required[T: BaseModel](model: type[T], value: BaseModel) -> T:
    if not isinstance(value, model):
        raise TypeError(f"expected {model.__name__}, got {type(value).__name__}")
    return value

__all__ = [
    "json",
    "sqlite3",
    "Iterator",
    "contextmanager",
    "UTC",
    "datetime",
    "Path",
    "Any",
    "Self",
    "BaseModel",
    "ValidationError",
    "AdapterPackage",
    "AdjudicationOutcome",
    "AgentMessage",
    "Assumption",
    "CapabilityGrant",
    "CapabilityReceipt",
    "CaseFile",
    "CompiledPrompt",
    "ContextDebtRecord",
    "ContextRequest",
    "ContradictionReport",
    "DebateSummary",
    "DebateTurn",
    "DistilledInstructionProposal",
    "EvidenceCoverageScore",
    "EvidenceReference",
    "ExitDisciplineCheck",
    "GatewayConfig",
    "GatewayRuntimeState",
    "Handoff",
    "HandoffQualityScore",
    "HumanDelegationPoint",
    "InstructionRegistryReceipt",
    "InstructionPromotionReview",
    "InstructionProvenance",
    "InstructionSource",
    "InstructionSourceRegistration",
    "InstructionSourceRegistry",
    "InstructionSourceSnapshot",
    "IntentLock",
    "KnowledgeFreshnessProbe",
    "KnownTrap",
    "MemoryDiff",
    "MemoryImpactPreview",
    "MemoryProposal",
    "NegativeKnowledge",
    "PluginCapabilityGrant",
    "PluginDescriptor",
    "PluginProbation",
    "PluginReceipt",
    "PolicyEnvelope",
    "ProjectProfile",
    "PromotedInstructionConstraint",
    "RecoverySession",
    "RedTeamFinding",
    "ReferenceIntegration",
    "ReviewRequest",
    "ReviewResult",
    "RunDelta",
    "RunOutput",
    "RuntimeCriticFinding",
    "ScopeChangeRequest",
    "ScopeChangeResult",
    "ScratchpadRecord",
    "SkillInvocationContext",
    "SkillPackage",
    "SkillRegistry",
    "TaskRequest",
    "TaskRun",
    "ToolResultAttestation",
    "UnknownRecord",
    "WorkerResult",
    "WorkGraphEvent",
    "CONTRACT_REGISTRY",
    "ContractModel",
    "CraikPaths",
    "ensure_craik_home",
    "contains_unredacted_secret",
    "CONTRACT_KINDS",
    "CURRENT_MIGRATION",
    "DATABASE_NAME",
    "MIGRATION_RECOVERY_GUIDANCE",
    "LocalStoreError",
    "LocalStoreCorruptError",
    "LocalStoreMigrationError",
    "UnredactedSecretError",
    "UnknownContractError",
    "LocalStoreCore",
    "_apply_migrations",
    "_cast_list",
    "_cast_optional",
    "_cast_required",
    "_kind_for_schema",
    "_parse_payload",
    "_record_migration",
    "_reject_unredacted_secrets",
    "_utc_now",
]
