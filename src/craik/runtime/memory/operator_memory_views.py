"""Memory impact operator view formatters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from craik.contracts.models import (
    FactValue,
    MemoryFactReference,
    MemoryImpactPreview,
    MemoryProposal,
)
from craik.runtime.policy.redaction import redact
from craik.runtime.policy.text import sanitize_runtime_text


@dataclass(frozen=True)
class MemoryImpactPreviewSnapshot:
    """Operator-visible memory impact preview state."""

    preview: MemoryImpactPreview
    proposals: list[MemoryProposal] = field(default_factory=list)
    policy_envelope_id: str | None = None
    receipt_ids: list[str] = field(default_factory=list)


def format_memory_impact_preview_view(snapshot: MemoryImpactPreviewSnapshot) -> list[str]:
    """Format memory impact without treating proposals as accepted facts."""
    preview = snapshot.preview
    lines = [
        f"Memory Impact Preview: {preview.id}",
        f"Task: {preview.task_id}",
        f"Policy: {snapshot.policy_envelope_id or 'none'}",
        f"Receipts: {_join_or_none(snapshot.receipt_ids)}",
        "",
        "Proposed Memory Writes",
    ]
    if not snapshot.proposals:
        lines.append("- none")
    else:
        for proposal in sorted(snapshot.proposals, key=lambda item: item.id):
            lines.extend(
                [
                    f"- {proposal.id} [{proposal.status}/{proposal.operation}]",
                    f"  Fact: {_format_fact_reference(proposal.fact)}",
                    f"  Evidence: {_join_or_none([item.id for item in proposal.evidence])}",
                    f"  Run: {proposal.run_id or 'none'}",
                    f"  Step: {proposal.step_id or 'none'}",
                    f"  Handoff: {proposal.handoff_id or 'none'}",
                ]
            )

    lines.extend(["", "Facts To Add"])
    lines.extend(_format_memory_fact_references(preview.facts_to_add))
    lines.extend(["", "Facts To Invalidate"])
    lines.extend(_format_memory_fact_references(preview.facts_to_invalidate))
    lines.extend(["", "Evidence Gaps", *_format_items(preview.evidence_missing)])
    lines.extend(["", "Contradiction Risks"])
    if not preview.likely_contradictions:
        lines.append("- none")
    else:
        for contradiction in sorted(
            preview.likely_contradictions,
            key=lambda item: (item.entity, item.relation, item.proposed_value),
        ):
            lines.extend(
                [
                    f"- {_safe_redacted(contradiction.entity)} "
                    f"{_safe_redacted(contradiction.relation)}",
                    f"  Existing: {_safe_redacted(contradiction.existing_value)}",
                    f"  Proposed: {_safe_redacted(contradiction.proposed_value)}",
                    f"  Reason: {_safe(contradiction.reason)}",
                ]
            )
    lines.extend(["", "Scope Summary", *_format_mapping(preview.scope_summary)])
    return lines


def _join_or_none(items: Sequence[str]) -> str:
    if not items:
        return "none"
    return ", ".join(_safe(item) for item in items)


def _format_items(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {_safe(item)}" for item in items]


def _format_mapping(items: Mapping[Any, float | int | str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {_safe(str(key))}: {_safe(str(items[key]))}" for key in sorted(items, key=str)]


def _format_memory_fact_references(
    items: Sequence[MemoryFactReference],
) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {_format_fact_reference(item)}" for item in items]


def _format_fact_reference(fact: FactValue | MemoryFactReference) -> str:
    return (
        f"{_safe_redacted(fact.entity)} {_safe_redacted(fact.relation)}="
        f"{_safe_redacted(str(fact.value))!r} source={_safe_redacted(fact.source)} "
        f"scope={fact.scope} trust={fact.trust_class}"
    )


def _safe_redacted(value: str) -> str:
    return _safe(str(redact(value).value))


def _safe(value: str) -> str:
    return sanitize_runtime_text(value)
