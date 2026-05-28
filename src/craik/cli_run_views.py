"""Payload shaping helpers for `craik run` inspection commands."""

from __future__ import annotations

from typing import Any

from craik.cli_run_support import next_allowed_action
from craik.contracts.models import TaskRun
from craik.runtime.store import LocalStore


def run_inspection_payload(
    store: LocalStore,
    run: TaskRun,
    *,
    include_outputs: bool,
) -> dict[str, Any]:
    outputs = [output for output in store.list_run_outputs() if output.run_id == run.id]
    receipts = [
        receipt for receipt in store.list_receipts() if receipt.id in _run_receipt_ids(run, outputs)
    ]
    proposals = [
        proposal
        for proposal in store.list_proposals()
        if proposal.id in {item for output in outputs for item in output.memory_proposal_ids}
    ]
    handoff = store.get_handoff(run.handoff_id) if run.handoff_id else None
    return {
        "run": run.model_dump(mode="json", by_alias=True),
        "status": run.status,
        "phase": run.phase,
        "stop_reason": run.stop_reason,
        "next_allowed_action": next_allowed_action(run),
        "receipts": [receipt.model_dump(mode="json", by_alias=True) for receipt in receipts],
        "outputs": [
            _run_output_payload(output, include_outputs=include_outputs) for output in outputs
        ],
        "memory_proposals": [
            proposal.model_dump(mode="json", by_alias=True) for proposal in proposals
        ],
        "handoff": handoff.model_dump(mode="json", by_alias=True) if handoff else None,
        "runner_metadata": run.runner_metadata,
    }


def _run_output_payload(output: Any, *, include_outputs: bool) -> dict[str, Any]:
    payload = output.model_dump(mode="json", by_alias=True)
    if include_outputs:
        return dict(payload)
    return {
        "id": payload["id"],
        "run_id": payload["run_id"],
        "step_result_id": payload["step_result_id"],
        "phase": payload["phase"],
        "summary": payload["summary"],
        "diagnostics": payload["diagnostics"],
        "receipt_ids": payload["receipt_ids"],
        "memory_proposal_ids": payload["memory_proposal_ids"],
        "artifacts": payload["artifacts"],
        "redacted": payload["redacted"],
    }


def _run_receipt_ids(run: TaskRun, outputs: list[Any]) -> set[str]:
    output_receipt_ids = [receipt for output in outputs for receipt in output.receipt_ids]
    return {*run.receipt_ids, *output_receipt_ids}
