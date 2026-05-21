"""Known trap and negative knowledge helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from craik.contracts.models import ContradictionReport, KnownTrap, NegativeKnowledge
from craik.runtime.policy.redaction import redact
from craik.runtime.store import LocalStore


def active_known_traps(
    store: LocalStore,
    project_id: str,
    *,
    now: datetime | None = None,
) -> list[KnownTrap]:
    """Return active, unexpired, uncontradicted traps for a project."""
    current = now or datetime.now(UTC)
    return sorted(
        (
            trap
            for trap in store.list_known_traps()
            if trap.status == "active"
            and (trap.project_id is None or trap.project_id == project_id)
            and (trap.expires_at is None or trap.expires_at > current)
        ),
        key=lambda trap: trap.id,
    )


def record_known_trap(
    store: LocalStore,
    *,
    kind: str,
    statement: str,
    avoidance: str,
    evidence_ids: list[str],
    project_id: str | None = None,
    task_id: str | None = None,
    handoff_ids: list[str] | None = None,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> KnownTrap:
    """Persist an evidence-backed known trap for future case files."""
    created_at = now or datetime.now(UTC)
    trap = KnownTrap(
        id=_record_id("known_trap", project_id or task_id or "global", statement, created_at),
        project_id=project_id,
        task_id=task_id,
        kind=kind,  # type: ignore[arg-type]
        statement=_clean(statement),
        avoidance=_clean(avoidance),
        evidence_ids=evidence_ids,
        handoff_ids=handoff_ids or [],
        created_at=created_at,
        expires_at=expires_at,
    )
    store.put_known_trap(trap)
    return trap


def known_trap_summaries(
    store: LocalStore,
    project_id: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Return deterministic onboarding/case-file summaries for active traps."""
    return [
        f"{trap.statement} Avoidance: {trap.avoidance}"
        for trap in active_known_traps(store, project_id, now=now)
    ]


def active_negative_knowledge(
    store: LocalStore,
    project_id: str,
    *,
    now: datetime | None = None,
) -> list[NegativeKnowledge]:
    """Return unexpired negative knowledge for a project."""
    current = now or datetime.now(UTC)
    return sorted(
        (
            knowledge
            for knowledge in store.list_negative_knowledge()
            if (knowledge.project_id is None or knowledge.project_id == project_id)
            and (knowledge.expires_at is None or knowledge.expires_at > current)
            and not knowledge.contradiction_ids
        ),
        key=lambda knowledge: knowledge.id,
    )


def record_negative_knowledge(
    store: LocalStore,
    *,
    statement: str,
    scope: str,
    trust_class: str,
    evidence_ids: list[str],
    project_id: str | None = None,
    task_id: str | None = None,
    handoff_ids: list[str] | None = None,
    contradicted_fact: str | None = None,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> NegativeKnowledge:
    """Persist evidence-backed negative knowledge and open a contradiction when supplied."""
    created_at = now or datetime.now(UTC)
    contradictions: list[str] = []
    if contradicted_fact:
        contradiction_id = _record_id(
            "contradiction_negative",
            project_id or task_id or "global",
            statement,
            created_at,
        )
        contradiction = ContradictionReport(
            id=contradiction_id,
            task_id=task_id,
            facts=[_clean(contradicted_fact), _clean(statement)],
            summary=(
                "Negative knowledge contradicts existing positive evidence: "
                f"{_clean(statement)}"
            ),
            evidence_ids=evidence_ids,
            proposed_resolution="Review evidence and adjudicate which assertion remains valid.",
            created_at=created_at,
        )
        store.put_contradiction(contradiction)
        contradictions.append(contradiction.id)
    knowledge = NegativeKnowledge(
        id=_record_id(
            "negative_knowledge",
            project_id or task_id or "global",
            statement,
            created_at,
        ),
        project_id=project_id,
        task_id=task_id,
        statement=_clean(statement),
        scope=_clean(scope),
        trust_class=trust_class,  # type: ignore[arg-type]
        evidence_ids=evidence_ids,
        handoff_ids=handoff_ids or [],
        contradiction_ids=contradictions,
        created_at=created_at,
        expires_at=expires_at,
    )
    store.put_negative_knowledge(knowledge)
    return knowledge


def negative_knowledge_summaries(
    store: LocalStore,
    project_id: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Return deterministic case-file summaries for active negative knowledge."""
    return [
        f"Negative knowledge: {knowledge.statement} Scope: {knowledge.scope}"
        for knowledge in active_negative_knowledge(store, project_id, now=now)
    ]


def _clean(value: str) -> str:
    redacted = redact(value).value
    return re.sub(r"\s+", " ", redacted).strip()


def _record_id(prefix: str, scope: str, text: str, created_at: datetime) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", _clean(text).lower()).strip("_")[:48] or "record"
    timestamp = created_at.strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{scope}_{slug}_{timestamp}"
