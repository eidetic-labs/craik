"""v0.5.0 continuity summaries for case files and prompts."""

from __future__ import annotations

from craik.runtime.memory.freshness import stale_risk_warnings
from craik.runtime.store import LocalStore
from craik.runtime.work.known_traps import (
    active_known_traps,
    active_negative_knowledge,
    known_trap_summaries,
    negative_knowledge_summaries,
)
from craik.runtime.work.scratchpad import (
    active_scratchpad_records,
    context_request_summaries,
    open_context_requests,
    unknown_summaries,
    unresolved_unknowns,
)


def v05_stale_risks(store: LocalStore, *, task_id: str, project_id: str) -> list[str]:
    """Return operator-facing v0.5 continuity risks for case files."""
    probes = [
        probe
        for probe in store.list_knowledge_freshness_probes()
        if probe.task_id == task_id or probe.project_id == project_id
    ]
    return [
        *known_trap_summaries(store, project_id),
        *negative_knowledge_summaries(store, project_id),
        *unknown_summaries(store, task_id),
        *context_request_summaries(store, task_id),
        *stale_risk_warnings(probes),
    ]


def v05_context_budget(store: LocalStore, *, task_id: str, project_id: str) -> dict[str, object]:
    """Return structured v0.5 continuity metadata for case-file context budgets."""
    traps = active_known_traps(store, project_id)
    negatives = active_negative_knowledge(store, project_id)
    scratchpad = active_scratchpad_records(store, task_id)
    unknowns = unresolved_unknowns(store, task_id)
    context_requests = open_context_requests(store, task_id)
    probes = [
        probe
        for probe in store.list_knowledge_freshness_probes()
        if probe.task_id == task_id or probe.project_id == project_id
    ]
    return {
        "known_trap_ids": [trap.id for trap in traps],
        "negative_knowledge_ids": [item.id for item in negatives],
        "scratchpad_record_ids": [record.id for record in scratchpad],
        "unknown_ids": [record.id for record in unknowns],
        "context_request_ids": [request.id for request in context_requests],
        "freshness_probe_ids": [probe.id for probe in probes],
    }
