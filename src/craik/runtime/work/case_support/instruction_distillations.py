"""Instruction distillation evidence entries for case files."""

from __future__ import annotations

from typing import Any

from craik.runtime.instruction_approval import list_governing
from craik.runtime.store import LocalStore

_DISTILLATION_CATEGORY_ORDER = {
    "policy": 0,
    "security_rule": 1,
    "boundary": 2,
    "command": 3,
    "instruction": 4,
    "handoff_rule": 5,
    "memory_rule": 6,
    "preference": 7,
    "stale_risk": 8,
}


def governing_distillations(store: LocalStore, project_id: str) -> list[dict[str, Any]]:
    """Return case-file entries for governing distilled instructions."""
    proposal_by_id = {
        proposal.id: proposal for proposal in store.list_distilled_instruction_proposals()
    }
    entries = []
    for constraint in list_governing(store, project_id=project_id):
        proposal = proposal_by_id.get(constraint.proposal_id)
        if proposal is None:
            continue
        provenance = [
            store.get_instruction_provenance(provenance_id)
            for provenance_id in proposal.provenance_ids
        ]
        review = store.get_instruction_promotion_review(f"promotion_review_{proposal.id}")
        entries.append(
            {
                "id": proposal.id,
                "constraint_id": constraint.id,
                "source_id": proposal.source_id,
                "snapshot_id": proposal.snapshot_id,
                "category": proposal.category,
                "statement": proposal.statement,
                "provenance": [
                    {
                        "id": item.id,
                        "path": item.path,
                        "start_line": item.start_line,
                        "end_line": item.end_line,
                        "start_column": item.start_column,
                        "end_column": item.end_column,
                        "summary": item.summary,
                        "excerpt_hash": item.excerpt_hash,
                    }
                    for item in provenance
                    if item is not None
                ],
                "approval_receipt": (
                    review.model_dump(mode="json", by_alias=True) if review is not None else None
                ),
            }
        )
    return sorted(
        entries,
        key=lambda item: (
            _DISTILLATION_CATEGORY_ORDER.get(str(item["category"]), 99),
            str(item["source_id"]),
            str(item["id"]),
        ),
    )
