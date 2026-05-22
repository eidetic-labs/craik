"""Read-only top-level operator surface overview."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OperatorSurfaceSection:
    """Read-only operator surface navigation summary."""

    id: str
    title: str
    status: str
    count: int
    summary: str
    command: str
    contract_kinds: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OperatorSurfaceSnapshot:
    """Top-level operator surface state assembled from local-store records."""

    project_id: str | None
    read_only: bool
    sections: list[OperatorSurfaceSection] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def build_operator_surface_snapshot(
    store: Any,
    *,
    project_id: str | None = None,
) -> OperatorSurfaceSnapshot:
    """Build the read-only operator surface overview from persisted local state."""
    tasks = _filter_project(store.list_tasks(), project_id=project_id)
    task_ids = {task.id for task in tasks}

    graph_events = _filter_project(
        store.list_graph_events(),
        project_id=project_id,
        task_ids=task_ids,
    )
    handoffs = _filter_project(store.list_handoffs(), project_id=project_id, task_ids=task_ids)
    receipts = _filter_project(store.list_receipts(), project_id=project_id, task_ids=task_ids)
    plugin_receipts = _filter_project(
        store.list_plugin_receipts(),
        project_id=project_id,
        task_ids=task_ids,
    )
    contradictions = _filter_project(
        store.list_contradictions(),
        project_id=project_id,
        task_ids=task_ids,
    )
    delegations = _filter_project(
        store.list_human_delegations(),
        project_id=project_id,
        task_ids=task_ids,
    )
    context_requests = _filter_project(
        store.list_context_requests(),
        project_id=project_id,
        task_ids=task_ids,
    )
    evidence = _filter_project(store.list_evidence(), project_id=project_id, task_ids=task_ids)
    assumptions = _filter_project(
        store.list_assumptions(),
        project_id=project_id,
        task_ids=task_ids,
    )
    memory_previews = _filter_project(
        store.list_memory_impact_previews(),
        project_id=project_id,
        task_ids=task_ids,
    )
    handoff_scores = _filter_project(
        store.list_handoff_quality_scores(),
        project_id=project_id,
        task_ids=task_ids,
    )
    evidence_scores = _filter_project(
        store.list_evidence_coverage_scores(),
        project_id=project_id,
        task_ids=task_ids,
    )
    critic_findings = _filter_project(
        store.list_runtime_critic_findings(),
        project_id=project_id,
        task_ids=task_ids,
    )
    red_team_findings = _filter_project(
        store.list_red_team_findings(),
        project_id=project_id,
        task_ids=task_ids,
    )
    instruction_sources = store.list_instruction_sources()
    instruction_snapshots = store.list_instruction_source_snapshots()
    instruction_provenance = store.list_instruction_provenance()
    instruction_proposals = store.list_distilled_instruction_proposals()
    instruction_reviews = store.list_instruction_promotion_reviews()
    known_traps = _filter_project(
        store.list_known_traps(),
        project_id=project_id,
        task_ids=task_ids,
    )
    negative_knowledge = _filter_project(
        store.list_negative_knowledge(),
        project_id=project_id,
        task_ids=task_ids,
    )
    run_deltas = _filter_project(
        store.list_run_deltas(),
        project_id=project_id,
        task_ids=task_ids,
    )
    recovery_sessions = _filter_project(
        store.list_recovery_sessions(),
        project_id=project_id,
        task_ids=task_ids,
    )

    inbox_count = len(contradictions) + len(delegations) + len(context_requests)
    instruction_count = (
        len(instruction_sources)
        + len(instruction_snapshots)
        + len(instruction_provenance)
        + len(instruction_proposals)
        + len(instruction_reviews)
    )
    quality_count = (
        len(handoff_scores)
        + len(evidence_scores)
        + len(critic_findings)
        + len(red_team_findings)
    )

    sections = [
        OperatorSurfaceSection(
            id="overview",
            title="Overview",
            status="ready",
            count=len(tasks),
            summary=f"{len(tasks)} task(s) visible in the selected scope.",
            command=_operator_command("overview", project_id),
            contract_kinds=["craik.task_request"],
        ),
        OperatorSurfaceSection(
            id="work-graph",
            title="Work Graph",
            status="ready" if graph_events else "empty",
            count=len(graph_events),
            summary=f"{len(graph_events)} graph event(s) available for export or inspection.",
            command=_operator_command("work-graph", project_id),
            contract_kinds=["craik.work_graph_event"],
        ),
        OperatorSurfaceSection(
            id="handoffs",
            title="Handoffs",
            status=_presence_status(handoffs),
            count=len(handoffs),
            summary=f"{len(handoffs)} handoff(s) link summaries, risks, receipts, and next steps.",
            command=_operator_command("handoffs", project_id),
            contract_kinds=["craik.handoff"],
        ),
        OperatorSurfaceSection(
            id="receipts",
            title="Receipts",
            status=_presence_status([*receipts, *plugin_receipts]),
            count=len(receipts) + len(plugin_receipts),
            summary=(
                f"{len(receipts)} capability receipt(s) and "
                f"{len(plugin_receipts)} plugin receipt(s)."
            ),
            command=_operator_command("receipts", project_id),
            contract_kinds=["craik.capability_receipt", "craik.plugin_receipt"],
        ),
        OperatorSurfaceSection(
            id="inbox",
            title="Inbox",
            status="attention" if inbox_count else "empty",
            count=inbox_count,
            summary=(
                f"{len(contradictions)} contradiction(s), {len(delegations)} delegation(s), "
                f"and {len(context_requests)} context request(s)."
            ),
            command=_operator_command("inbox", project_id),
            contract_kinds=[
                "craik.contradiction_report",
                "craik.human_delegation_point",
                "craik.context_request",
            ],
        ),
        OperatorSurfaceSection(
            id="evidence",
            title="Evidence",
            status=_presence_status([*evidence, *assumptions, *memory_previews]),
            count=len(evidence) + len(assumptions) + len(memory_previews),
            summary=(
                f"{len(evidence)} evidence reference(s), {len(assumptions)} assumption(s), "
                f"and {len(memory_previews)} memory impact preview(s)."
            ),
            command=_operator_command("evidence", project_id),
            contract_kinds=[
                "craik.evidence_reference",
                "craik.assumption",
                "craik.memory_impact_preview",
            ],
        ),
        OperatorSurfaceSection(
            id="quality",
            title="Quality",
            status=_quality_status(
                handoff_scores,
                evidence_scores,
                critic_findings,
                red_team_findings,
            ),
            count=quality_count,
            summary=(
                f"{len(handoff_scores)} handoff score(s), {len(evidence_scores)} evidence "
                f"score(s), {len(critic_findings)} critic finding(s), and "
                f"{len(red_team_findings)} red-team finding(s)."
            ),
            command=_operator_command("quality", project_id),
            contract_kinds=[
                "craik.handoff_quality_score",
                "craik.evidence_coverage_score",
                "craik.runtime_critic_finding",
                "craik.red_team_finding",
            ],
        ),
        OperatorSurfaceSection(
            id="instructions",
            title="Instructions",
            status=_presence_status(
                [
                    *instruction_sources,
                    *instruction_snapshots,
                    *instruction_provenance,
                    *instruction_proposals,
                    *instruction_reviews,
                ]
            ),
            count=instruction_count,
            summary=(
                f"{len(instruction_sources)} source(s), {len(instruction_snapshots)} "
                f"snapshot(s), {len(instruction_provenance)} provenance record(s), "
                f"{len(instruction_proposals)} proposal(s), and "
                f"{len(instruction_reviews)} review(s)."
            ),
            command=_operator_command("instructions", project_id),
            contract_kinds=[
                "craik.instruction_source",
                "craik.instruction_source_snapshot",
                "craik.instruction_provenance",
                "craik.distilled_instruction_proposal",
                "craik.instruction_promotion_review",
            ],
        ),
        OperatorSurfaceSection(
            id="traps",
            title="Known Traps",
            status="attention" if known_traps or negative_knowledge else "empty",
            count=len(known_traps) + len(negative_knowledge),
            summary=(
                f"{len(known_traps)} known trap(s) and "
                f"{len(negative_knowledge)} negative knowledge record(s)."
            ),
            command=_operator_command("traps", project_id),
            contract_kinds=["craik.known_trap", "craik.negative_knowledge"],
        ),
        OperatorSurfaceSection(
            id="run-deltas",
            title="Run Deltas",
            status=_presence_status([*run_deltas, *recovery_sessions]),
            count=len(run_deltas) + len(recovery_sessions),
            summary=(
                f"{len(run_deltas)} run delta(s) and "
                f"{len(recovery_sessions)} recovery session(s)."
            ),
            command=_operator_command("run-deltas", project_id),
            contract_kinds=["craik.run_delta", "craik.recovery_session"],
        ),
    ]
    return OperatorSurfaceSnapshot(
        project_id=project_id,
        read_only=True,
        sections=sections,
        notes=[
            "Missing data is unavailable, not inferred.",
            "Counts come from local-store read helpers only.",
        ],
    )


def format_operator_surface_overview(snapshot: OperatorSurfaceSnapshot) -> list[str]:
    """Format the shared operator surface overview."""
    lines = [
        "Operator Surface",
        f"Project: {snapshot.project_id or 'all'}",
        f"Read-only: {snapshot.read_only}",
        "",
        "Views",
    ]
    if not snapshot.sections:
        lines.append("- none")
    else:
        for section in snapshot.sections:
            lines.extend(
                [
                    f"- {section.title} ({section.id}) [{section.status}] count={section.count}",
                    f"  Command: {section.command}",
                    f"  Contracts: {_join_or_none(section.contract_kinds)}",
                    f"  Summary: {section.summary}",
                ]
            )

    lines.extend(["", "Notes"])
    lines.extend(_format_items(snapshot.notes))
    return lines


def _filter_project(
    records: list[Any],
    *,
    project_id: str | None,
    task_ids: set[str] | None = None,
) -> list[Any]:
    if project_id is None:
        return records
    scoped: list[Any] = []
    for record in records:
        record_project_id = getattr(record, "project_id", None)
        if record_project_id is not None:
            if record_project_id == project_id:
                scoped.append(record)
            continue
        record_task_id = getattr(record, "task_id", None)
        if record_task_id is not None:
            if task_ids is not None and record_task_id in task_ids:
                scoped.append(record)
            continue
        scoped.append(record)
    return scoped


def _presence_status(records: list[Any]) -> str:
    return "ready" if records else "empty"


def _quality_status(
    handoff_scores: list[Any],
    evidence_scores: list[Any],
    critic_findings: list[Any],
    red_team_findings: list[Any],
) -> str:
    if any(getattr(score, "band", None) == "poor" for score in handoff_scores):
        return "blocked"
    if any(getattr(score, "band", None) == "poor" for score in evidence_scores):
        return "blocked"
    if any(
        getattr(finding, "blocking", False)
        and getattr(finding, "review_status", None) != "adjudicated"
        for finding in red_team_findings
    ):
        return "blocked"
    if any(
        getattr(finding, "review_status", None) == "reviewable"
        and getattr(finding, "severity", None) in {"high", "critical"}
        for finding in critic_findings
    ):
        return "reviewable"
    if any(getattr(score, "band", None) == "adequate" for score in handoff_scores):
        return "reviewable"
    if any(getattr(score, "band", None) == "adequate" for score in evidence_scores):
        return "reviewable"
    return "clear"


def _operator_command(view: str, project_id: str | None) -> str:
    command = f"craik operator overview --section {view}"
    if project_id is not None:
        command = f"{command} --project {project_id}"
    return command


def _format_items(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]


def _join_or_none(items: list[str]) -> str:
    if not items:
        return "none"
    return ", ".join(items)
