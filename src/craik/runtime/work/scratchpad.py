"""Expiring scratchpad and first-class unknown helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from craik.contracts.models import (
    CapabilityReceipt,
    ContextRequest,
    ReceiptResult,
    ScratchpadRecord,
    UnknownRecord,
)
from craik.runtime.policy.redaction import redact
from craik.runtime.store import LocalStore

DEFAULT_SCRATCHPAD_TTL = timedelta(hours=6)


def active_scratchpad_records(
    store: LocalStore,
    task_id: str,
    *,
    now: datetime | None = None,
) -> list[ScratchpadRecord]:
    """Return active scratchpad entries that have not expired."""
    current = now or datetime.now(UTC)
    return sorted(
        (
            record
            for record in store.list_scratchpad_records()
            if record.task_id == task_id
            and record.status == "active"
            and record.expires_at > current
        ),
        key=lambda record: record.id,
    )


def write_scratchpad_record(
    store: LocalStore,
    *,
    task_id: str,
    owner: str,
    note: str,
    project_id: str | None = None,
    evidence_ids: list[str] | None = None,
    ttl: timedelta = DEFAULT_SCRATCHPAD_TTL,
    now: datetime | None = None,
) -> ScratchpadRecord:
    """Persist an expiring scratchpad note through the production store path."""
    created_at = now or datetime.now(UTC)
    record = ScratchpadRecord(
        id=_record_id("scratchpad", task_id, note, created_at),
        task_id=task_id,
        project_id=project_id,
        owner=_clean(owner),
        note=_clean(note),
        evidence_ids=evidence_ids or [],
        created_at=created_at,
        expires_at=created_at + ttl,
    )
    store.put_scratchpad_record(record)
    return record


def unresolved_unknowns(store: LocalStore, task_id: str) -> list[UnknownRecord]:
    """Return unresolved unknowns for a task."""
    return sorted(
        (
            record
            for record in store.list_unknown_records()
            if record.task_id == task_id and record.status == "unresolved"
        ),
        key=lambda record: record.id,
    )


def record_unknown(
    store: LocalStore,
    *,
    task_id: str,
    question: str,
    next_action: str,
    needed_resolution: str,
    project_id: str | None = None,
    owner: str | None = None,
    evidence_ids: list[str] | None = None,
    now: datetime | None = None,
) -> UnknownRecord:
    """Persist an unresolved unknown as first-class continuation context."""
    created_at = now or datetime.now(UTC)
    record = UnknownRecord(
        id=_record_id("unknown", task_id, question, created_at),
        task_id=task_id,
        project_id=project_id,
        owner=_clean(owner) if owner else None,
        question=_clean(question),
        needed_resolution=needed_resolution,  # type: ignore[arg-type]
        next_action=_clean(next_action),
        evidence_ids=evidence_ids or [],
        created_at=created_at,
    )
    store.put_unknown_record(record)
    return record


def resolve_unknown(
    store: LocalStore,
    unknown_id: str,
    *,
    answer: str,
    resolved_by: str,
    receipt_id: str | None = None,
    now: datetime | None = None,
) -> UnknownRecord:
    """Mark an unknown resolved and link the operator receipt that resolved it."""
    existing = store.get_unknown_record(unknown_id)
    if existing is None:
        raise ValueError(f"unknown unknown record: {unknown_id}")
    resolved_at = now or datetime.now(UTC)
    resolved_receipt_id = receipt_id or _resolution_receipt(
        store,
        task_id=existing.task_id,
        actor=resolved_by,
        capability="unknown.resolve",
        target=unknown_id,
        summary=f"Resolved unknown {unknown_id}.",
        created_at=resolved_at,
    ).id
    updated = existing.model_copy(
        update={
            "status": "resolved",
            "resolved_answer": _clean(answer),
            "resolved_at": resolved_at,
            "resolved_by_receipt_id": resolved_receipt_id,
        }
    )
    store.put_unknown_record(updated)
    return updated


def request_context(
    store: LocalStore,
    *,
    task_id: str,
    requester: str,
    kind: str,
    question: str,
    needed_for: str,
    project_id: str | None = None,
    handoff_id: str | None = None,
    recovery_session_id: str | None = None,
    unknown_id: str | None = None,
    now: datetime | None = None,
) -> ContextRequest:
    """Persist a structured context request that can block exit discipline."""
    created_at = now or datetime.now(UTC)
    request = ContextRequest(
        id=_record_id("context_request", task_id, question, created_at),
        task_id=task_id,
        project_id=project_id,
        requester=_clean(requester),
        kind=kind,  # type: ignore[arg-type]
        question=_clean(question),
        needed_for=_clean(needed_for),
        handoff_id=handoff_id,
        recovery_session_id=recovery_session_id,
        unknown_id=unknown_id,
        created_at=created_at,
    )
    store.put_context_request(request)
    return request


def fulfill_context_request(
    store: LocalStore,
    request_id: str,
    *,
    fulfilled_by: str,
    receipt_id: str | None = None,
    now: datetime | None = None,
) -> ContextRequest:
    """Mark a context request fulfilled and retain operator receipt linkage."""
    existing = store.get_context_request(request_id)
    if existing is None:
        raise ValueError(f"unknown context request: {request_id}")
    fulfilled_at = now or datetime.now(UTC)
    fulfilled_receipt_id = receipt_id or _resolution_receipt(
        store,
        task_id=existing.task_id,
        actor=fulfilled_by,
        capability="context_request.fulfill",
        target=request_id,
        summary=f"Fulfilled context request {request_id}.",
        created_at=fulfilled_at,
    ).id
    updated = existing.model_copy(
        update={
            "status": "fulfilled",
            "fulfilled_by": _clean(fulfilled_by),
            "fulfilled_at": fulfilled_at,
            "fulfilled_by_receipt_id": fulfilled_receipt_id,
        }
    )
    store.put_context_request(updated)
    return updated


def unknown_summaries(store: LocalStore, task_id: str) -> list[str]:
    """Return deterministic summaries for handoffs and case-file stale risks."""
    return [
        f"Unknown unresolved: {record.question} Next action: {record.next_action}"
        for record in unresolved_unknowns(store, task_id)
    ]


def open_context_requests(store: LocalStore, task_id: str) -> list[ContextRequest]:
    """Return open context requests for a task."""
    return sorted(
        (
            request
            for request in store.list_context_requests()
            if request.task_id == task_id and request.status == "open"
        ),
        key=lambda request: request.id,
    )


def context_request_summaries(store: LocalStore, task_id: str) -> list[str]:
    """Return deterministic operator summaries for open context requests."""
    return [
        f"Context request open: {request.question} Needed for: {request.needed_for}"
        for request in open_context_requests(store, task_id)
    ]


def _clean(value: str) -> str:
    redacted = redact(value).value
    return re.sub(r"\s+", " ", redacted).strip()


def _record_id(prefix: str, task_id: str, text: str, created_at: datetime) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", _clean(text).lower()).strip("_")[:48] or "record"
    timestamp = created_at.strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{task_id}_{slug}_{timestamp}"


def _resolution_receipt(
    store: LocalStore,
    *,
    task_id: str,
    actor: str,
    capability: str,
    target: str,
    summary: str,
    created_at: datetime,
) -> CapabilityReceipt:
    receipt = CapabilityReceipt(
        id=f"receipt_{capability.replace('.', '_')}_{target}",
        task_id=task_id,
        actor=_clean(actor),
        capability=capability,
        target=target,
        policy_profile="strict",
        reason=summary,
        result=ReceiptResult(status="passed", summary=summary),
        created_at=created_at,
    )
    return store.put_receipt(receipt)
