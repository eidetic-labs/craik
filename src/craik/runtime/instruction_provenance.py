"""Instruction provenance extraction from parsed source statements."""

from __future__ import annotations

import hashlib

from craik.contracts.models import InstructionProvenance, InstructionSourceSnapshot
from craik.runtime.projects.instruction_ingestion import ParsedInstructionSource
from craik.runtime.store import LocalStore


class InstructionProvenanceExtractionError(RuntimeError):
    """Raised when parsed source content cannot be linked to a snapshot."""


def extract_instruction_provenance(
    parsed: ParsedInstructionSource,
    *,
    snapshot: InstructionSourceSnapshot,
    project_id: str,
) -> list[InstructionProvenance]:
    """Build deterministic provenance records for parsed instruction statements."""
    if snapshot.project_id != project_id:
        raise InstructionProvenanceExtractionError(
            f"snapshot project {snapshot.project_id!r} does not match {project_id!r}"
        )
    if snapshot.path != parsed.path:
        raise InstructionProvenanceExtractionError(
            f"snapshot path {snapshot.path!r} does not match parsed path {parsed.path!r}"
        )
    if snapshot.hash_status == "missing":
        raise InstructionProvenanceExtractionError("missing snapshots cannot produce provenance")

    records = [
        InstructionProvenance(
            id=_provenance_id(snapshot, index, statement.text),
            project_id=project_id,
            source_id=snapshot.source_id,
            snapshot_id=snapshot.id,
            path=parsed.path,
            start_line=statement.start_line,
            end_line=statement.end_line,
            start_column=statement.start_column,
            end_column=statement.end_column,
            summary=_summary(statement.text),
            excerpt_hash=_excerpt_hash(statement.text),
            captured_at=snapshot.captured_at,
        )
        for index, statement in enumerate(parsed.statements, start=1)
    ]
    return sorted(records, key=lambda record: record.id)


def persist_instruction_provenance(
    store: LocalStore,
    parsed: ParsedInstructionSource,
    *,
    snapshot: InstructionSourceSnapshot,
    project_id: str,
) -> list[InstructionProvenance]:
    """Extract and persist provenance records for parsed instruction statements."""
    records = extract_instruction_provenance(parsed, snapshot=snapshot, project_id=project_id)
    for record in records:
        store.put_instruction_provenance(record)
    return records


def _provenance_id(
    snapshot: InstructionSourceSnapshot,
    index: int,
    statement_text: str,
) -> str:
    digest = hashlib.sha256(statement_text.encode("utf-8")).hexdigest()[:12]
    return f"instruction_provenance_{snapshot.source_id}_{snapshot.id}_{index:04d}_{digest}"


def _summary(statement_text: str) -> str:
    first_line = next(
        (line.strip() for line in statement_text.splitlines() if line.strip()),
        "",
    )
    return first_line[:200]


def _excerpt_hash(statement_text: str) -> str:
    return hashlib.sha256(statement_text.encode("utf-8")).hexdigest()
