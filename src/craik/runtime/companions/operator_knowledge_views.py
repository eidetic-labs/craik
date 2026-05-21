"""Read-only operator views for v0.5 knowledge resolution state."""

from __future__ import annotations

from dataclasses import dataclass, field

from craik.contracts.models import (
    CapabilityReceipt,
    ContextDebtRecord,
    ContextRequest,
    UnknownRecord,
)


@dataclass(frozen=True)
class KnowledgeResolutionSnapshot:
    """Operator-visible v0.5 knowledge resolution state."""

    context_debt: list[ContextDebtRecord] = field(default_factory=list)
    unknowns: list[UnknownRecord] = field(default_factory=list)
    context_requests: list[ContextRequest] = field(default_factory=list)
    receipts: list[CapabilityReceipt] = field(default_factory=list)


def format_knowledge_resolution_view(snapshot: KnowledgeResolutionSnapshot) -> list[str]:
    """Format unknown, context-request, and context-debt resolution provenance."""
    receipt_ids = {receipt.id for receipt in snapshot.receipts}
    lines = ["Knowledge Resolution", "", "Context Debt"]
    if not snapshot.context_debt:
        lines.append("- none")
    else:
        for debt in sorted(snapshot.context_debt, key=lambda item: (item.status, item.id)):
            lines.extend(
                [
                    f"- {debt.id} [{debt.status}/{debt.kind}] task={debt.task_id}",
                    f"  Summary: {debt.summary}",
                    f"  Next Action: {debt.next_action or 'none'}",
                    "  Resolution Receipt: "
                    f"{_format_resolution_receipt(debt.resolved_by_receipt_id, receipt_ids)}",
                ]
            )

    lines.extend(["", "Unknowns"])
    if not snapshot.unknowns:
        lines.append("- none")
    else:
        for unknown in sorted(snapshot.unknowns, key=lambda item: (item.status, item.id)):
            lines.extend(
                [
                    f"- {unknown.id} [{unknown.status}] task={unknown.task_id}",
                    f"  Question: {unknown.question}",
                    f"  Next Action: {unknown.next_action}",
                    f"  Answer: {unknown.resolved_answer or 'none'}",
                    "  Resolution Receipt: "
                    f"{_format_resolution_receipt(unknown.resolved_by_receipt_id, receipt_ids)}",
                ]
            )

    lines.extend(["", "Context Requests"])
    if not snapshot.context_requests:
        lines.append("- none")
    else:
        for request in sorted(snapshot.context_requests, key=lambda item: (item.status, item.id)):
            lines.extend(
                [
                    f"- {request.id} [{request.status}/{request.kind}] task={request.task_id}",
                    f"  Question: {request.question}",
                    f"  Needed For: {request.needed_for}",
                    f"  Fulfilled By: {request.fulfilled_by or 'none'}",
                    "  Fulfillment Receipt: "
                    f"{_format_resolution_receipt(request.fulfilled_by_receipt_id, receipt_ids)}",
                ]
            )
    return lines


def _format_resolution_receipt(receipt_id: str | None, receipt_ids: set[str]) -> str:
    if receipt_id is None:
        return "unresolved"
    if receipt_id in receipt_ids:
        return f"{receipt_id} (verified)"
    return f"{receipt_id} (missing or tampered)"
