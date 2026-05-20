"""Public loop result and error types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from craik.contracts.models import (
    CapabilityReceipt,
    RunnerStepRequest,
    RunnerStepResult,
    TaskRun,
)
from craik.runtime.work.run_outputs import RunOutputCapture


class LoopExecutionError(RuntimeError):
    """Base error for governed loop execution failures."""


class LoopPolicyBlockedError(LoopExecutionError):
    """Raised when policy blocks a side-effect step."""


class LoopMaxIterationsError(LoopExecutionError):
    """Raised when the loop reaches its iteration bound."""


class LoopTimeBudgetExceededError(LoopExecutionError):
    """Raised when the loop exhausts its wall-clock budget."""


class LoopProviderBudgetExceededError(LoopExecutionError):
    """Raised when the loop exhausts its provider token budget."""


class RunnerStepHandler(Protocol):
    """Minimal runner boundary for one loop step."""

    def run_step(
        self,
        request: RunnerStepRequest,
        *,
        stream_callback: Callable[[str], None] | None = None,
    ) -> RunnerStepResult:
        """Execute one step request and return a normalized result."""


@dataclass(frozen=True)
class LoopExecutionResult:
    """Summary of a completed or stopped loop execution."""

    run: TaskRun
    step_results: list[RunnerStepResult]
    output_captures: list[RunOutputCapture]
    receipts: list[CapabilityReceipt]
