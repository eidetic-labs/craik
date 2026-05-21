"""Operator view formatters for work artifacts."""

from __future__ import annotations

from craik.contracts.models import (
    Assumption,
    CapabilityReceipt,
    ContradictionReport,
    EvidenceReference,
    Handoff,
    PluginReceipt,
    WorkGraphEdge,
    WorkGraphExport,
    WorkGraphNode,
)


def format_evidence_assumption_view(
    evidence: list[EvidenceReference],
    assumptions: list[Assumption],
) -> list[str]:
    """Format evidence and assumptions while keeping assumptions distinct."""
    lines = [f"Evidence: {len(evidence)}", ""]
    lines.extend(_format_evidence(item) for item in sorted(evidence, key=lambda item: item.id))
    if not evidence:
        lines.append("- none")
    lines.extend(["", f"Assumptions: {len(assumptions)}", ""])
    lines.extend(
        _format_assumption(item) for item in sorted(assumptions, key=lambda item: item.id)
    )
    if not assumptions:
        lines.append("- none")
    return lines


def format_contradiction_inbox(reports: list[ContradictionReport]) -> list[str]:
    """Format a read-only contradiction inbox."""
    lines = [f"Contradiction Inbox: {len(reports)}", ""]
    if not reports:
        return [*lines, "- none"]
    for report in sorted(reports, key=lambda item: (item.status, item.id)):
        lines.extend(
            [
                f"- {report.id} [{report.status}]",
                f"  Task: {report.task_id}",
                f"  Owner: {report.owner or 'unassigned'}",
                f"  Summary: {report.summary}",
                f"  Proposed Resolution: {report.proposed_resolution}",
                f"  Affected Artifacts: {_join_or_none(report.affected_artifacts)}",
                f"  Evidence: {_join_or_none(report.evidence_ids)}",
            ]
        )
    return lines


def format_receipt_viewer(receipt: CapabilityReceipt | PluginReceipt) -> list[str]:
    """Format a redacted capability or plugin receipt."""
    if isinstance(receipt, PluginReceipt):
        lines = [
            f"Plugin Receipt: {receipt.id}",
            f"Task: {receipt.task_id}",
            f"Actor: {receipt.actor}",
            f"Plugin: {receipt.plugin_descriptor_id}",
            f"Probation: {receipt.plugin_probation_id or 'None'}",
            f"Action: {receipt.action}",
            f"Trust Boundary: {receipt.trust_boundary}",
            f"Status: {receipt.result.status}",
            f"Summary: {receipt.result.summary}",
            f"Redacted: {receipt.redacted}",
            "",
            "Capability Grants",
            *_format_items(receipt.capability_grant_ids),
            "",
            "Evidence",
            *_format_items(receipt.evidence_ids),
            "",
            "Handoffs",
            *_format_items(receipt.handoff_ids),
        ]
        return lines
    return [
        f"Capability Receipt: {receipt.id}",
        f"Task: {receipt.task_id}",
        f"Actor: {receipt.actor}",
        f"Capability: {receipt.capability}",
        f"Target: {receipt.target}",
        f"Policy: {receipt.policy_profile}",
        f"Status: {receipt.result.status}",
        f"Reason: {receipt.reason}",
        f"Summary: {receipt.result.summary}",
        f"Redacted: {receipt.redacted}",
    ]


def format_handoff_viewer(handoff: Handoff) -> list[str]:
    """Format a redacted handoff viewer."""
    lines = [
        f"Handoff: {handoff.id}",
        f"Task: {handoff.task_id}",
        f"Project: {handoff.project_id}",
        f"Status: {handoff.status}",
        f"Agent: {handoff.agent}",
        f"Summary: {handoff.summary}",
        "",
        "Completed Actions",
        *_format_items(handoff.completed_actions),
        "",
        "Next Steps",
        *_format_items(handoff.next_steps),
        "",
        "Receipts",
        *_format_items(handoff.receipt_ids),
        "",
        "Evidence And Artifacts",
        *_format_items([*handoff.artifacts, *handoff.files_changed]),
        "",
        "Risks",
        *_format_items(handoff.risks),
        "",
        "Open Follow-Ups",
        *_format_items(
            [
                *handoff.context_debt,
                *handoff.assumptions,
                *handoff.contradictions_opened,
                *handoff.open_human_delegation_ids,
            ]
        ),
    ]
    return lines


def format_work_graph_explorer(export: WorkGraphExport) -> list[str]:
    """Format a deterministic work graph explorer view."""
    lines = [
        f"Work Graph: {export.id}",
        f"Task: {export.task_id or 'all'}",
        f"Nodes: {len(export.nodes)}",
        f"Edges: {len(export.edges)}",
        "",
        "Nodes",
    ]
    lines.extend(_format_node(node) for node in export.nodes)
    lines.append("")
    lines.append("Edges")
    lines.extend(_format_edge(edge) for edge in export.edges)
    return lines


def _format_node(node: WorkGraphNode) -> str:
    task = f" task={node.task_id}" if node.task_id else ""
    return f"- {node.id} [{node.type}]{task}: {node.label}"


def _format_edge(edge: WorkGraphEdge) -> str:
    metadata = _format_metadata(edge.metadata)
    suffix = f" {metadata}" if metadata else ""
    return f"- {edge.from_node} -[{edge.type}]-> {edge.to_node}{suffix}"


def _format_metadata(metadata: dict[str, object]) -> str:
    if not metadata:
        return ""
    parts = [f"{key}={metadata[key]}" for key in sorted(metadata)]
    return "(" + ", ".join(parts) + ")"


def _format_items(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]


def _format_evidence(evidence: EvidenceReference) -> str:
    captured = evidence.captured_at.isoformat() if evidence.captured_at else "unknown"
    return (
        f"- {evidence.id} [{evidence.kind}] source={evidence.source} "
        f"locator={evidence.locator} captured={captured}: {evidence.summary}"
    )


def _format_assumption(assumption: Assumption) -> str:
    evidence = _join_or_none(assumption.evidence_ids)
    return (
        f"- {assumption.id} [{assumption.status}] task={assumption.task_id} "
        f"confidence={assumption.confidence:.2f} evidence={evidence}: "
        f"{assumption.statement}"
    )


def _join_or_none(items: list[str]) -> str:
    if not items:
        return "none"
    return ", ".join(items)
