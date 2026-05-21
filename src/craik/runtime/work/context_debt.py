"""First-class context debt records derived from case files and handoffs."""

from __future__ import annotations

from datetime import UTC, datetime

from craik.contracts.models import CaseFile, ContextDebtRecord
from craik.runtime.store import LocalStore
from craik.runtime.work.scratchpad import _clean, _resolution_receipt


def records_from_case_file(
    case_file: CaseFile | None,
    *,
    task_id: str,
    project_id: str | None = None,
    handoff_id: str | None = None,
    owner: str | None = None,
    created_at: datetime | None = None,
) -> list[ContextDebtRecord]:
    """Derive deterministic context debt records from a case file."""
    now = created_at or datetime.now(UTC)
    if case_file is None:
        return [
            ContextDebtRecord(
                id=_debt_id(task_id, "missing_case_file", "case_file"),
                task_id=task_id,
                project_id=project_id,
                handoff_id=handoff_id,
                kind="missing_case_file",
                summary="No case file was available for this handoff.",
                owner=owner,
                next_action="Rebuild the case file before relying on this handoff.",
                created_at=now,
            )
        ]

    project = project_id
    records: list[ContextDebtRecord] = []
    omitted = case_file.context_budget.get("docs_omitted", [])
    if isinstance(omitted, list) and omitted:
        paths = sorted(str(item) for item in omitted)
        records.append(
            ContextDebtRecord(
                id=_debt_id(case_file.task_id, "omitted_doc", ",".join(paths)),
                task_id=case_file.task_id,
                project_id=project,
                case_file_id=case_file.id,
                handoff_id=handoff_id,
                kind="omitted_doc",
                summary=f"Documentation omitted by context budget: {', '.join(paths)}",
                owner=owner,
                next_action="Review omitted documentation before making related claims.",
                omitted_doc_paths=paths,
                created_at=now,
            )
        )
    excluded = case_file.context_budget.get("docs_excluded", [])
    if isinstance(excluded, list) and excluded:
        paths = sorted(
            str(item.get("path", item)) if isinstance(item, dict) else str(item)
            for item in excluded
        )
        records.append(
            ContextDebtRecord(
                id=_debt_id(case_file.task_id, "excluded_doc", ",".join(paths)),
                task_id=case_file.task_id,
                project_id=project,
                case_file_id=case_file.id,
                handoff_id=handoff_id,
                kind="excluded_doc",
                summary=f"Documentation excluded by discovery rules: {', '.join(paths)}",
                owner=owner,
                next_action="Confirm excluded documentation is not needed for this scope.",
                omitted_doc_paths=paths,
                created_at=now,
            )
        )
    if case_file.github_state.get("status") == "not_loaded":
        records.append(
            ContextDebtRecord(
                id=_debt_id(case_file.task_id, "missing_external_state", "github"),
                task_id=case_file.task_id,
                project_id=project,
                case_file_id=case_file.id,
                handoff_id=handoff_id,
                kind="missing_external_state",
                summary="GitHub state was not loaded into the case file.",
                owner=owner,
                next_action="Refresh GitHub issue and pull request state before continuing.",
                missing_external_state=["github"],
                created_at=now,
            )
        )
    if not case_file.facts:
        records.append(
            ContextDebtRecord(
                id=_debt_id(case_file.task_id, "missing_memory_facts", "facts"),
                task_id=case_file.task_id,
                project_id=project,
                case_file_id=case_file.id,
                handoff_id=handoff_id,
                kind="missing_memory_facts",
                summary="No memory facts were loaded into the case file.",
                owner=owner,
                next_action="Query configured memory before promoting new facts.",
                created_at=now,
            )
        )
    active_constraints = case_file.context_budget.get("active_instruction_constraints", [])
    if isinstance(active_constraints, list) and active_constraints:
        ids = sorted(
            str(item.get("id", item)) if isinstance(item, dict) else str(item)
            for item in active_constraints
        )
        records.append(
            ContextDebtRecord(
                id=_debt_id(
                    case_file.task_id,
                    "active_instruction_constraint",
                    ",".join(ids),
                ),
                task_id=case_file.task_id,
                project_id=project,
                case_file_id=case_file.id,
                handoff_id=handoff_id,
                kind="active_instruction_constraint",
                summary=f"Active instruction constraints carried forward: {', '.join(ids)}",
                owner=owner,
                next_action="Apply active instruction constraints to the next runtime context.",
                stale_instruction_ids=ids,
                created_at=now,
            )
        )
    for assumption in sorted(case_file.assumptions, key=lambda item: item.id):
        if assumption.status != "open":
            continue
        records.append(
            ContextDebtRecord(
                id=_debt_id(case_file.task_id, "unresolved_assumption", assumption.id),
                task_id=case_file.task_id,
                project_id=project,
                case_file_id=case_file.id,
                handoff_id=handoff_id,
                kind="unresolved_assumption",
                summary=f"Unresolved assumption carried forward: {assumption.statement}",
                owner=owner,
                next_action="Resolve or validate the assumption before promoting it as fact.",
                assumption_ids=[assumption.id],
                evidence_ids=assumption.evidence_ids,
                created_at=now,
            )
        )
    return records


def carry_forward_context_debt(
    records: list[ContextDebtRecord],
    *,
    handoff_id: str,
    created_at: datetime | None = None,
) -> list[ContextDebtRecord]:
    """Create carried-forward copies for a new handoff."""
    now = created_at or datetime.now(UTC)
    carried: list[ContextDebtRecord] = []
    for record in records:
        if record.status == "resolved":
            continue
        carried.append(
            record.model_copy(
                update={
                    "id": f"{record.id}_carried_{handoff_id}",
                    "handoff_id": handoff_id,
                    "status": "carried_forward",
                    "created_at": now,
                    "resolved_at": None,
                }
            )
        )
    return carried


def resolve_context_debt(
    store: LocalStore,
    debt_id: str,
    *,
    resolved_by: str,
    receipt_id: str | None = None,
    summary: str | None = None,
    now: datetime | None = None,
) -> ContextDebtRecord:
    """Mark a context debt record resolved and retain operator receipt linkage."""
    existing = store.get_context_debt_record(debt_id)
    if existing is None:
        raise ValueError(f"unknown context debt record: {debt_id}")
    resolved_at = now or datetime.now(UTC)
    resolution_summary = _clean(summary or f"Resolved context debt {debt_id}.")
    resolved_receipt_id = receipt_id or _resolution_receipt(
        store,
        task_id=existing.task_id,
        actor=resolved_by,
        capability="context_debt.resolve",
        target=debt_id,
        summary=resolution_summary,
        created_at=resolved_at,
    ).id
    updated = existing.model_copy(
        update={
            "status": "resolved",
            "resolved_at": resolved_at,
            "resolved_by_receipt_id": resolved_receipt_id,
        }
    )
    store.put_context_debt_record(updated)
    return updated


def context_debt_summaries(records: list[ContextDebtRecord]) -> list[str]:
    """Return deterministic handoff-facing context debt summaries."""
    return [record.summary for record in sorted(records, key=lambda record: record.id)]


def _debt_id(task_id: str, kind: str, key: str) -> str:
    safe_key = key.replace("/", "_").replace(":", "_").replace(",", "_")
    return f"context_debt_{task_id}_{kind}_{safe_key}"
