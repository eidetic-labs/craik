"""Instruction distillation orchestration and deterministic categorization."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import (
    DistilledInstructionCategory,
    DistilledInstructionProposal,
    InstructionSourceKind,
)
from craik.runtime.instruction_provenance import persist_instruction_provenance
from craik.runtime.instruction_snapshots import refresh_project_snapshots
from craik.runtime.instructions import list_sources
from craik.runtime.projects.instruction_ingestion import (
    InstructionStatement,
    parse_instruction_source,
)
from craik.runtime.projects.instruction_sources import (
    detect_instruction_contradictions,
    invalidate_stale_distillations,
)
from craik.runtime.store import LocalStore


@dataclass(frozen=True)
class CategorizationResult:
    """Deterministic category assignment for one instruction statement."""

    category: DistilledInstructionCategory | None
    confidence: float
    matched_rule: str


@dataclass(frozen=True)
class IngestionSummary:
    """Result counts from one project instruction ingestion pass."""

    project_id: str
    source_count: int
    snapshot_count: int
    provenance_count: int
    proposal_count: int
    unclassified_count: int
    invalidated_count: int = 0
    contradiction_count: int = 0
    skipped_existing_count: int = 0
    warnings: list[str] = field(default_factory=list)


class InstructionDistillationError(RuntimeError):
    """Raised when a project instruction ingestion pass cannot run."""


def categorize_instruction(
    statement: InstructionStatement,
    *,
    default_confidence: float = 0.6,
    source_kind: InstructionSourceKind | None = None,
) -> CategorizationResult:
    """Categorize one parsed instruction statement with deterministic rules."""
    text = _normalized(statement.text)
    if not text:
        return CategorizationResult(None, 0.0, "empty")
    if _contains(text, ("last updated", "stale", "outdated", "expired")):
        return CategorizationResult("stale_risk", default_confidence, "stale_risk_keyword")
    if _contains(text, ("secret", "credential", "token", "redact", "private key")):
        return CategorizationResult("security_rule", default_confidence, "security_keyword")
    if _contains(text, ("handoff", "review", "delegation", "delegate")):
        return CategorizationResult("handoff_rule", default_confidence, "handoff_keyword")
    if _contains(text, ("memory", "remember", "fact", "stigmem")):
        return CategorizationResult("memory_rule", default_confidence, "memory_keyword")
    if _contains(text, ("never", "do not", "must not", "boundary", "scope", "ownership")):
        return CategorizationResult("boundary", default_confidence, "boundary_keyword")
    if _contains(text, ("run", "execute", "call", "invoke", "command")):
        return CategorizationResult("command", default_confidence, "command_keyword")
    if _contains(text, ("prefer", "favor", "i want")):
        return CategorizationResult("preference", default_confidence, "preference_keyword")
    if source_kind == "policy_doc":
        return CategorizationResult("policy", default_confidence, "policy_doc_source")
    if _contains(text, ("must", "should", "always", "ensure")):
        return CategorizationResult("instruction", default_confidence, "imperative_keyword")
    return CategorizationResult(None, 0.0, "unclassified")


def ingest_project_instructions(
    store: LocalStore,
    project_id: str,
    *,
    now: datetime | None = None,
) -> IngestionSummary:
    """Run registered source ingestion through proposal persistence."""
    project = store.get_project(project_id)
    if project is None:
        raise InstructionDistillationError(f"unknown project: {project_id}")
    created_at = now or datetime.now(UTC)
    base_dir = Path(project.repo.local_path).expanduser().resolve()
    with store.transaction():
        sources = list_sources(store, project_id=project_id, active=True)
        snapshots = refresh_project_snapshots(store, project_id, now=created_at)
        invalidated = invalidate_stale_distillations(
            store,
            current_snapshots=snapshots,
        )
        snapshot_by_source = {snapshot.source_id: snapshot for snapshot in snapshots}

        provenance_count = 0
        proposal_count = 0
        skipped_existing_count = 0
        unclassified_count = 0
        warnings: list[str] = []
        for source in sources:
            snapshot = snapshot_by_source.get(source.id)
            if snapshot is None or snapshot.hash_status in {"missing", "oversize"}:
                continue
            parsed = parse_instruction_source(source, base_dir=base_dir)
            provenance = persist_instruction_provenance(
                store,
                parsed,
                snapshot=snapshot,
                project_id=project_id,
            )
            provenance_count += len(provenance)
            for statement, record in zip(parsed.statements, provenance, strict=True):
                result = categorize_instruction(statement, source_kind=parsed.source_kind)
                if result.category is None:
                    unclassified_count += 1
                    warnings.append(
                        f"Unclassified instruction candidate {record.id} in {record.path}: "
                        f"{record.summary}"
                    )
                    continue
                proposal = _proposal(
                    project_id=project_id,
                    snapshot_id=snapshot.id,
                    source_id=snapshot.source_id,
                    statement=statement.text,
                    provenance_id=record.id,
                    category=result.category,
                    confidence=result.confidence,
                    matched_rule=result.matched_rule,
                    created_at=created_at,
                )
                if store.get_distilled_instruction_proposal(proposal.id) is not None:
                    skipped_existing_count += 1
                    continue
                store.put_distilled_instruction_proposal(proposal)
                proposal_count += 1
        reports = detect_instruction_contradictions(
            store,
            task_id=f"instruction_distillation_{project_id}_{created_at.isoformat()}",
            owner="agent:instruction-distillation",
        )

        return IngestionSummary(
            project_id=project_id,
            source_count=len(sources),
            snapshot_count=len(snapshots),
            provenance_count=provenance_count,
            proposal_count=proposal_count,
            invalidated_count=len(invalidated),
            contradiction_count=len(reports),
            skipped_existing_count=skipped_existing_count,
            unclassified_count=unclassified_count,
            warnings=warnings,
        )


def _proposal(
    *,
    project_id: str,
    snapshot_id: str,
    source_id: str,
    statement: str,
    provenance_id: str,
    category: DistilledInstructionCategory,
    confidence: float,
    matched_rule: str,
    created_at: datetime,
) -> DistilledInstructionProposal:
    evidence_ids = [provenance_id]
    return DistilledInstructionProposal(
        id=f"distilled_instruction_{provenance_id}",
        project_id=project_id,
        source_id=source_id,
        snapshot_id=snapshot_id,
        category=category,
        statement=statement,
        rationale=f"Deterministic categorization matched {matched_rule}.",
        confidence=confidence,
        provenance_ids=[provenance_id],
        evidence_ids=evidence_ids,
        created_at=created_at,
    )


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)
