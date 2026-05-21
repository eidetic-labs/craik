"""Recovery mode summaries for agents resuming work."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from craik.contracts.models import (
    RecoverySession,
    RecoveryStatus,
    RunDelta,
    RunDeltaItem,
)
from craik.runtime.store import LocalStore


@dataclass(frozen=True)
class RecoveryBuilder:
    """Build and persist recovery summaries from local continuity records."""

    store: LocalStore

    def build(
        self,
        *,
        project_id: str,
        task_id: str | None = None,
        decided_by: str | None = None,
        persist: bool = True,
    ) -> RecoverySession:
        """Build a recovery session for a project or one task."""
        now = datetime.now(UTC)
        task_ids = _task_ids(self.store, project_id, task_id)
        handoffs = sorted(
            (
                handoff
                for handoff in self.store.list_handoffs()
                if handoff.project_id == project_id
                and (task_id is None or handoff.task_id == task_id)
            ),
            key=lambda handoff: (handoff.created_at, handoff.id),
        )
        case_files = sorted(
            (
                case_file
                for case_file in self.store.list_case_files()
                if case_file.task_id in task_ids
            ),
            key=lambda case_file: case_file.id,
        )
        receipts = sorted(
            (
                receipt
                for receipt in self.store.list_receipts()
                if receipt.task_id in task_ids
            ),
            key=lambda receipt: (receipt.created_at, receipt.id),
        )
        open_contradictions = sorted(
            (
                contradiction
                for contradiction in self.store.list_contradictions()
                if contradiction.status == "open"
                and (contradiction.task_id is None or contradiction.task_id in task_ids)
            ),
            key=lambda contradiction: contradiction.id,
        )
        active_constraints = sorted(
            (
                constraint
                for constraint in self.store.list_promoted_instruction_constraints()
                if constraint.project_id == project_id and constraint.active
            ),
            key=lambda constraint: constraint.id,
        )

        previous_handoff = handoffs[-2] if len(handoffs) > 1 else None
        current_handoff = handoffs[-1] if handoffs else None
        changes = _changes(
            current_handoff_id=current_handoff.id if current_handoff else None,
            previous_handoff_id=previous_handoff.id if previous_handoff else None,
            case_file_ids=[case_file.id for case_file in case_files],
            receipt_ids=[receipt.id for receipt in receipts],
            contradiction_ids=[contradiction.id for contradiction in open_contradictions],
            active_instruction_constraint_ids=[constraint.id for constraint in active_constraints],
        )
        status = _status(
            has_handoff=current_handoff is not None,
            open_contradictions=len(open_contradictions),
            active_constraints=len(active_constraints),
        )
        required_actions = _required_actions(status, open_contradictions, active_constraints)
        stale_risks = _stale_risks(open_contradictions, active_constraints)
        delta = RunDelta(
            id=_scoped_id("run_delta", project_id, task_id),
            project_id=project_id,
            task_id=task_id,
            previous_handoff_id=previous_handoff.id if previous_handoff else None,
            current_handoff_id=current_handoff.id if current_handoff else None,
            case_file_ids=[case_file.id for case_file in case_files],
            receipt_ids=[receipt.id for receipt in receipts],
            contradiction_ids=[contradiction.id for contradiction in open_contradictions],
            active_instruction_constraint_ids=[constraint.id for constraint in active_constraints],
            changes=changes,
            summary=_delta_summary(status, changes),
            created_at=now,
        )
        session = RecoverySession(
            id=_scoped_id("recovery_session", project_id, task_id),
            project_id=project_id,
            task_id=task_id,
            status=status,
            run_delta_id=delta.id,
            resume_summary=_resume_summary(status, current_handoff.id if current_handoff else None),
            required_actions=required_actions,
            stale_risks=stale_risks,
            handoff_ids=[handoff.id for handoff in handoffs],
            case_file_ids=delta.case_file_ids,
            receipt_ids=delta.receipt_ids,
            contradiction_ids=delta.contradiction_ids,
            active_instruction_constraint_ids=delta.active_instruction_constraint_ids,
            decided_by=decided_by,
            created_at=now,
        )
        if persist:
            self.store.put_run_delta(delta)
            self.store.put_recovery_session(session)
        return session


def render_recovery_markdown(session: RecoverySession, delta: RunDelta) -> str:
    """Render a deterministic recovery summary for a resuming agent."""
    lines = [
        f"# Recovery Session: {session.id}",
        "",
        f"- Status: {session.status}",
        f"- Project: {session.project_id}",
        f"- Task: {session.task_id or 'all'}",
        f"- Run Delta: {session.run_delta_id}",
        "",
        "## Summary",
        "",
        session.resume_summary,
        "",
        "## Required Actions",
        "",
        *_bullets(session.required_actions),
        "",
        "## Stale Risks",
        "",
        *_bullets(session.stale_risks),
        "",
        "## Changes",
        "",
        *_bullets([change.summary for change in delta.changes]),
    ]
    return "\n".join(lines) + "\n"


def _task_ids(store: LocalStore, project_id: str, task_id: str | None) -> set[str]:
    if task_id is not None:
        return {task_id}
    return {task.id for task in store.list_tasks() if task.project_id == project_id}


def _status(
    *,
    has_handoff: bool,
    open_contradictions: int,
    active_constraints: int,
) -> RecoveryStatus:
    if not has_handoff:
        return "missing_prior_context"
    if open_contradictions or active_constraints:
        return "changed_state"
    return "clean_resume"


def _changes(
    *,
    current_handoff_id: str | None,
    previous_handoff_id: str | None,
    case_file_ids: list[str],
    receipt_ids: list[str],
    contradiction_ids: list[str],
    active_instruction_constraint_ids: list[str],
) -> list[RunDeltaItem]:
    changes: list[RunDeltaItem] = []
    if current_handoff_id is None:
        changes.append(
            RunDeltaItem(
                kind="removed",
                entity_type="handoff",
                entity_id="missing_handoff",
                summary="No prior handoff is available for recovery.",
            )
        )
    else:
        changes.append(
            RunDeltaItem(
                kind="unchanged" if previous_handoff_id is None else "updated",
                entity_type="handoff",
                entity_id=current_handoff_id,
                previous_ref=previous_handoff_id,
                current_ref=current_handoff_id,
                summary=f"Latest handoff available: {current_handoff_id}.",
            )
        )
    for case_file_id in case_file_ids:
        changes.append(
            RunDeltaItem(
                kind="unchanged",
                entity_type="case_file",
                entity_id=case_file_id,
                current_ref=case_file_id,
                summary=f"Case file available: {case_file_id}.",
            )
        )
    for receipt_id in receipt_ids:
        changes.append(
            RunDeltaItem(
                kind="unchanged",
                entity_type="receipt",
                entity_id=receipt_id,
                current_ref=receipt_id,
                summary=f"Receipt available: {receipt_id}.",
            )
        )
    for contradiction_id in contradiction_ids:
        changes.append(
            RunDeltaItem(
                kind="created",
                entity_type="contradiction",
                entity_id=contradiction_id,
                current_ref=contradiction_id,
                summary=f"Open contradiction requires review: {contradiction_id}.",
            )
        )
    for constraint_id in active_instruction_constraint_ids:
        changes.append(
            RunDeltaItem(
                kind="created",
                entity_type="instruction_constraint",
                entity_id=constraint_id,
                current_ref=constraint_id,
                summary=f"Active instruction constraint applies: {constraint_id}.",
            )
        )
    return changes


def _required_actions(
    status: RecoveryStatus,
    open_contradictions: Sequence[object],
    active_constraints: Sequence[object],
) -> list[str]:
    if status == "clean_resume":
        return []
    actions: list[str] = []
    if status == "missing_prior_context":
        actions.append("Rebuild a case file and establish a handoff before resuming.")
    if open_contradictions:
        actions.append("Review open contradictions before promoting new facts.")
    if active_constraints:
        actions.append("Apply active instruction constraints to the resumed runtime context.")
    return actions


def _stale_risks(
    open_contradictions: Sequence[object],
    active_constraints: Sequence[object],
) -> list[str]:
    risks: list[str] = []
    if open_contradictions:
        risks.append("Open contradictions may invalidate prior assumptions or facts.")
    if active_constraints:
        risks.append(
            "Instruction constraints may change how previous handoffs should be interpreted."
        )
    return risks


def _delta_summary(status: RecoveryStatus, changes: list[RunDeltaItem]) -> str:
    return f"Recovery status is {status}; {len(changes)} continuity records were summarized."


def _resume_summary(status: RecoveryStatus, handoff_id: str | None) -> str:
    if status == "clean_resume":
        return f"Resume from latest handoff {handoff_id}."
    if status == "changed_state":
        return f"Resume from latest handoff {handoff_id} after reviewing changed state."
    return "Prior context is incomplete; rebuild recovery context before continuing."


def _scoped_id(prefix: str, project_id: str, task_id: str | None) -> str:
    scope = task_id or project_id
    safe_scope = scope.replace(":", "_").replace("/", "_")
    return f"{prefix}_{safe_scope}"


def _bullets(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]
