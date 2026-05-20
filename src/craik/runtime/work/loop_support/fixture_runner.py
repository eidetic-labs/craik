"""Deterministic loop runner used by local tests and fixtures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from craik.contracts.models import (
    RunnerResultStatus,
    RunnerStepRequest,
    RunnerStepResult,
)


@dataclass
class FixtureStepRunner:
    """Deterministic step runner for local tests."""

    statuses: list[RunnerResultStatus] = field(default_factory=list)

    def run_step(
        self,
        request: RunnerStepRequest,
        *,
        stream_callback: Callable[[str], None] | None = None,
    ) -> RunnerStepResult:
        _ = stream_callback
        status = self.statuses.pop(0) if self.statuses else "completed"
        return RunnerStepResult(
            id=f"runner_step_result_{request.run_id}_{request.phase}_{request.id}",
            request_id=request.id,
            run_id=request.run_id,
            task_id=request.task_id,
            phase=request.phase,
            runner=request.runner,
            status=status,
            summary=f"Fixture {request.phase} step {status}.",
            observed_output={"phase": request.phase, "status": status},
            diagnostics=[] if status in {"completed", "partial"} else [f"fixture {status}"],
            created_at=datetime.now(UTC),
        )
