"""Instruction-source registration API for runtime distillation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from craik.contracts.models import (
    INSTRUCTION_SOURCE_DEFAULT_PATHS,
    InstructionRegistryReceipt,
    InstructionSource,
    InstructionSourceKind,
    InstructionSourceRegistration,
    InstructionSourceRegistry,
    InstructionTrustBoundary,
)
from craik.runtime.store import LocalStore


class InstructionRegistrationError(RuntimeError):
    """Raised when an instruction source cannot be registered."""


@dataclass(frozen=True)
class InstructionRegistrationResult:
    """Artifacts written by one instruction-source registration."""

    source: InstructionSource
    registration: InstructionSourceRegistration
    receipt: InstructionRegistryReceipt
    registry: InstructionSourceRegistry


def register_source(
    store: LocalStore,
    *,
    project_id: str,
    kind: InstructionSourceKind,
    owner: str,
    registered_by: str,
    path: str | None = None,
    source_id: str | None = None,
    trust_boundary: InstructionTrustBoundary = "project",
    content_hash: str | None = None,
    active: bool = True,
    policy_envelope_id: str | None = None,
    notes: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    now: datetime | None = None,
) -> InstructionRegistrationResult:
    """Register one declared instruction source and persist its audit receipt."""
    registered_at = now or datetime.now(UTC)
    declared_path = _declared_path(kind, path)
    resolved_source_id = source_id or _source_id(project_id, kind, declared_path)
    if store.get_instruction_source(resolved_source_id) is not None:
        raise InstructionRegistrationError(
            f"instruction source already registered: {resolved_source_id}"
        )

    source = InstructionSource(
        id=resolved_source_id,
        project_id=project_id,
        kind=kind,
        path=declared_path,
        owner=owner,
        trust_boundary=trust_boundary,
        active=active,
        declared_by=registered_by,
        registered_by=registered_by,
        registered_at=registered_at,
        content_hash=content_hash,
        policy_envelope_id=policy_envelope_id,
        notes=notes or [],
        metadata=dict(metadata or {}),
        created_at=registered_at,
    )
    registration = InstructionSourceRegistration(
        id=f"instruction_source_registration_{resolved_source_id}",
        project_id=project_id,
        source_id=source.id,
        kind=kind,
        path=declared_path,
        owner=owner,
        registered_by=registered_by,
        registered_at=registered_at,
        trust_boundary=trust_boundary,
        content_hash=content_hash,
        policy_envelope_id=policy_envelope_id,
        notes=notes or [],
        metadata=dict(metadata or {}),
    )
    receipt = InstructionRegistryReceipt(
        id=f"instruction_registry_receipt_{resolved_source_id}",
        project_id=project_id,
        source_id=source.id,
        registration_id=registration.id,
        registered_by=registered_by,
        target=declared_path,
        summary=f"Registered {kind} instruction source at {declared_path}.",
        created_at=registered_at,
    )

    store.put_instruction_source(source)
    store.put_instruction_source_registration(registration)
    store.put_instruction_registry_receipt(receipt)
    registry = _upsert_project_registry(store, source, registered_at)
    return InstructionRegistrationResult(
        source=source,
        registration=registration,
        receipt=receipt,
        registry=registry,
    )


def list_sources(
    store: LocalStore,
    *,
    project_id: str | None = None,
    active: bool | None = None,
) -> list[InstructionSource]:
    """List registered instruction sources in stable order."""
    sources = store.list_instruction_sources()
    if project_id is not None:
        sources = [source for source in sources if source.project_id == project_id]
    if active is not None:
        sources = [source for source in sources if source.active is active]
    return sorted(sources, key=lambda source: (source.project_id, source.kind, source.path))


def _upsert_project_registry(
    store: LocalStore,
    source: InstructionSource,
    created_at: datetime,
) -> InstructionSourceRegistry:
    registry_id = f"instruction_source_registry_{source.project_id}"
    existing = store.get_instruction_source_registry(registry_id)
    sources = [] if existing is None else list(existing.sources)
    sources.append(source)
    sources = sorted(sources, key=lambda item: (item.kind, item.path, item.id))
    active_source_ids = [item.id for item in sources if item.active]
    declared_policy_doc_paths = sorted(
        item.path for item in sources if item.kind == "policy_doc"
    )
    registry = InstructionSourceRegistry(
        id=registry_id,
        project_id=source.project_id,
        sources=sources,
        active_source_ids=active_source_ids,
        declared_policy_doc_paths=declared_policy_doc_paths,
        created_at=existing.created_at if existing is not None else created_at,
    )
    store.put_instruction_source_registry(registry)
    return registry


def _declared_path(kind: InstructionSourceKind, path: str | None) -> str:
    default_path = INSTRUCTION_SOURCE_DEFAULT_PATHS[kind]
    declared_path = path if path is not None else default_path
    if not declared_path:
        raise InstructionRegistrationError(
            "policy_doc instruction sources require a declared path"
        )
    return declared_path


def _source_id(project_id: str, kind: InstructionSourceKind, path: str) -> str:
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    return f"instruction_source_{_slug(project_id)}_{kind}_{digest}"


def _slug(value: str) -> str:
    slugged = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slugged or "unknown"


__all__ = [
    "InstructionRegistrationError",
    "InstructionRegistrationResult",
    "list_sources",
    "register_source",
]
