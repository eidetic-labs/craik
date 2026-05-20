"""Replay helpers for resumed loop execution."""

from __future__ import annotations

from craik.contracts.models import RunOutput
from craik.runtime.work.loop_support.execution import stream_chunks_from_output
from craik.runtime.work.run_outputs import RunOutputCapture


def completed_step_capture(
    outputs: list[RunOutput],
    *,
    run_id: str,
    step_key: str,
) -> RunOutputCapture | None:
    """Return the captured output for a previously completed step."""
    for output in outputs:
        if output.run_id != run_id:
            continue
        if output.observed_output.get("idempotency_key") != step_key:
            continue
        return RunOutputCapture(
            output=output,
            proposals=[],
            skipped_reasons=["step already completed; reused durable output"],
            chunks=stream_chunks_from_output(output.observed_output),
        )
    return None
