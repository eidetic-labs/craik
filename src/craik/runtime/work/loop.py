"""Governed single-agent execution loop."""

from __future__ import annotations

from datetime import UTC, datetime

from craik.contracts.models import (
    CapabilityGrant,
    CapabilityReceipt,
    IntentLock,
    PolicyEnvelope,
    RunnerMetadata,
    RunnerStepRequest,
    RunnerStepResult,
    TaskRunStatus,
)
from craik.runtime.memory.memory import MemoryStore
from craik.runtime.policy.policy import denial_receipt
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.intent_locks import record_intent_lock_coordination_denial
from craik.runtime.work.loop_support.budgets import (
    raise_provider_budget_if_exhausted,
    raise_time_budget_if_exhausted,
)
from craik.runtime.work.loop_support.execution import (
    LoopStep,
    context_with_idempotency,
    context_with_message_history,
    credential_policy_context,
    default_loop_steps,
    intent_stop_reason,
    loop_step_key,
    message_history_from_context,
    provider_usage_total_tokens,
    request_id,
    result_with_idempotency_key,
    runtime_policy_context,
)
from craik.runtime.work.loop_support.execution import (
    operator_policy_decision as check_active_operator_policy,
)
from craik.runtime.work.loop_support.execution import (
    side_effect_receipt as build_side_effect_receipt,
)
from craik.runtime.work.loop_support.fixture_runner import FixtureStepRunner
from craik.runtime.work.loop_support.replay import completed_step_capture
from craik.runtime.work.loop_support.scope_control import record_scope_change_pause
from craik.runtime.work.loop_support.tool_dispatch import (
    attested_tool_message,
    dispatch_tool_call_side_effect,
    dispatchable_tool_calls,
    result_with_stream_chunks,
)
from craik.runtime.work.loop_support.types import (
    LoopExecutionError,
    LoopExecutionResult,
    LoopMaxIterationsError,
    LoopPolicyBlockedError,
    LoopProviderBudgetExceededError,
    LoopTimeBudgetExceededError,
    RunnerStepHandler,
)
from craik.runtime.work.run_outputs import (
    RunOutputCapture,
    RunOutputRecorder,
)
from craik.runtime.work.runs import RunTransition, TaskRunManager

__all__ = [
    "FixtureStepRunner", "LoopExecutionError", "LoopExecutionResult",
    "LoopMaxIterationsError", "LoopPolicyBlockedError", "LoopProviderBudgetExceededError",
    "LoopTimeBudgetExceededError", "LoopStep", "RunnerStepHandler", "SingleAgentLoopExecutor",
    "default_loop_steps",
]


class SingleAgentLoopExecutor:
    """Drive one agent through governed plan/act/observe/evaluate phases."""

    def __init__(
        self,
        *,
        store: LocalStore,
        memory: MemoryStore,
        runner: RunnerStepHandler,
    ) -> None:
        self.store = store
        self.memory = memory
        self.runner = runner
        self.runs = TaskRunManager(store)
        self.outputs = RunOutputRecorder(store, memory)

    def execute(
        self,
        *,
        task_id: str,
        case_file_id: str,
        policy: PolicyEnvelope,
        runner_metadata: RunnerMetadata,
        intent_lock: IntentLock | None = None,
        grants: list[CapabilityGrant] | None = None,
        steps: list[LoopStep] | None = None,
        max_iterations: int = 5,
        wall_clock_budget_seconds: float | None = None,
        provider_token_budget: int | None = None,
        started_at: datetime | None = None,
        resume_run_id: str | None = None,
        role_id: str | None = None,
        role_kind: str | None = None,
        initial_receipt_ids: list[str] | None = None,
    ) -> LoopExecutionResult:
        active_steps = steps or default_loop_steps()
        resuming = resume_run_id is not None
        run = (
            self.runs.prepare_resume(
                resume_run_id,
                max_iterations=max_iterations,
                at=started_at,
            )
            if resume_run_id is not None
            else self.runs.create(
                task_id=task_id,
                case_file_id=case_file_id,
                policy_envelope_id=policy.id,
                intent_lock_id=intent_lock.id if intent_lock else None,
                runner_id=runner_metadata.id,
                runner_mode=runner_metadata.mode,
                max_iterations=max_iterations,
                wall_clock_budget_seconds=wall_clock_budget_seconds,
                provider_token_budget=provider_token_budget,
                role_id=role_id,
                role_kind=role_kind,
                receipt_ids=initial_receipt_ids,
                created_at=started_at,
            )
        )
        receipts: list[CapabilityReceipt] = []
        step_results: list[RunnerStepResult] = []
        output_captures: list[RunOutputCapture] = []
        active_grants = grants or []
        iteration = run.iteration
        coordination_receipt = record_intent_lock_coordination_denial(
            self.store,
            run=run,
            policy=policy,
            actor=f"runner:{runner_metadata.id}",
            intent_lock=intent_lock,
            phase="start",
        )
        if coordination_receipt is not None:
            receipts.append(coordination_receipt)
            run = self.runs.transition(
                run.id,
                RunTransition(
                    status="blocked",
                    phase="stop",
                    iteration=0,
                    receipt_id=coordination_receipt.id,
                    stop_reason=coordination_receipt.reason,
                    at=datetime.now(UTC),
                ),
            )
            return LoopExecutionResult(run, step_results, output_captures, receipts)
        operator_policy_decision = check_active_operator_policy(policy)
        if not operator_policy_decision.allowed:
            receipt = denial_receipt(
                policy=policy,
                decision=operator_policy_decision,
                actor=f"runner:{runner_metadata.id}",
            )
            self.store.put_receipt(receipt)
            receipts.append(receipt)
            run = self.runs.transition(
                run.id,
                RunTransition(
                    status="blocked",
                    phase="stop",
                    iteration=0,
                    receipt_id=receipt.id,
                    stop_reason=receipt.reason,
                    at=datetime.now(UTC),
                ),
            )
            return LoopExecutionResult(run, step_results, output_captures, receipts)
        operator_policy = operator_policy_decision.receipt_metadata
        credential_policy = credential_policy_context(policy)

        for index, step in enumerate(active_steps, start=1):
            step_key = loop_step_key(run.id, index, step.phase)
            if resuming:
                existing_capture = self._completed_step_capture(run.id, step_key)
                if existing_capture is not None:
                    output_captures.append(existing_capture)
                    continue

            self._raise_time_budget_if_exhausted(run.id, iteration)

            self._raise_provider_budget_if_exhausted(run.id, iteration)

            coordination_receipt = record_intent_lock_coordination_denial(
                self.store,
                run=run,
                policy=policy,
                actor=f"runner:{runner_metadata.id}",
                intent_lock=intent_lock,
                phase=step.phase,
            )
            if coordination_receipt is not None:
                receipts.append(coordination_receipt)
                run = self.runs.transition(
                    run.id,
                    RunTransition(
                        status="blocked",
                        phase="stop",
                        iteration=index - 1,
                        receipt_id=coordination_receipt.id,
                        stop_reason=coordination_receipt.reason,
                        at=datetime.now(UTC),
                    ),
                )
                return LoopExecutionResult(run, step_results, output_captures, receipts)

            if iteration >= max_iterations:
                run = self.runs.transition(
                    run.id,
                    RunTransition(
                        status="interrupted",
                        phase="stop",
                        stop_reason=f"max iterations {max_iterations} reached",
                        at=datetime.now(UTC),
                    ),
                )
                raise LoopMaxIterationsError(run.stop_reason or "max iterations reached")

            scope_change = record_scope_change_pause(
                store=self.store,
                policy=policy,
                run=run,
                intent_lock=intent_lock,
                step=step,
                actor=f"runner:{runner_metadata.id}",
            )
            if scope_change is not None:
                if scope_change.receipt is not None:
                    receipts.append(scope_change.receipt)
                run = scope_change.run or self.runs.require(run.id)
                return LoopExecutionResult(run, step_results, output_captures, receipts)

            stop_reason = intent_stop_reason(intent_lock, step)
            if stop_reason is not None:
                run = self.runs.transition(
                    run.id,
                    RunTransition(
                        status="blocked",
                        phase="stop",
                        iteration=index - 1,
                        stop_reason=stop_reason,
                        at=datetime.now(UTC),
                    ),
                )
                return LoopExecutionResult(run, step_results, output_captures, receipts)

            side_effect_receipt = build_side_effect_receipt(
                policy=policy,
                grants=active_grants,
                step=step,
                actor=f"runner:{runner_metadata.id}",
            )
            if side_effect_receipt is not None:
                self.store.put_receipt(side_effect_receipt)
                receipts.append(side_effect_receipt)
                if side_effect_receipt.result.status == "denied":
                    run = self.runs.transition(
                        run.id,
                        RunTransition(
                            status="blocked",
                            phase="stop",
                            iteration=index - 1,
                            receipt_id=side_effect_receipt.id,
                            stop_reason=side_effect_receipt.reason,
                            at=datetime.now(UTC),
                        ),
                    )
                    return LoopExecutionResult(run, step_results, output_captures, receipts)

            message_history = message_history_from_context(step.context)
            step_context = runtime_policy_context(
                step.context,
                operator_policy=operator_policy,
                credential_policy=credential_policy,
            )
            tool_round = 0
            request = RunnerStepRequest(
                id="",
                run_id=run.id,
                task_id=task_id,
                phase=step.phase,
                runner=runner_metadata,
                policy_envelope_id=policy.id,
                intent_lock_id=intent_lock.id if intent_lock else None,
                capability_grant_ids=[grant.id for grant in active_grants],
                expected_output_schemas=["craik.runner_step_result"],
                input_prompt=step.input_prompt,
                context={},
                created_at=datetime.now(UTC),
            )
            while True:
                self._raise_time_budget_if_exhausted(run.id, iteration)
                self._raise_provider_budget_if_exhausted(run.id, iteration)

                if iteration >= max_iterations:
                    run = self.runs.transition(
                        run.id,
                        RunTransition(
                            status="interrupted",
                            phase="stop",
                            stop_reason=f"max iterations {max_iterations} reached",
                            at=datetime.now(UTC),
                        ),
                    )
                    raise LoopMaxIterationsError(run.stop_reason or "max iterations reached")

                request = request.model_copy(
                    update={
                        "id": request_id(run.id, index, step.phase, tool_round),
                        "context": context_with_message_history(
                            context_with_idempotency(
                                step_context,
                                step_key=step_key,
                                tool_round=tool_round,
                            ),
                            message_history,
                        ),
                        "created_at": datetime.now(UTC),
                    }
                )
                stream_chunks: list[str] = []
                result = self.runner.run_step(request, stream_callback=stream_chunks.append)
                iteration += 1
                if stream_chunks:
                    result = result_with_stream_chunks(result, stream_chunks)
                result = result_with_idempotency_key(result, step_key)
                token_delta = provider_usage_total_tokens(result.observed_output)
                if token_delta:
                    run = self.runs.transition(
                        run.id,
                        RunTransition(
                            provider_tokens_used_delta=token_delta,
                            at=datetime.now(UTC),
                        ),
                    )
                receipt_ids = list(result.receipt_ids)
                if side_effect_receipt is not None and side_effect_receipt.id not in receipt_ids:
                    receipt_ids.append(side_effect_receipt.id)

                tool_calls = dispatchable_tool_calls(result)
                tool_messages: list[dict[str, str]] = []
                denied_tool_receipt: CapabilityReceipt | None = None
                if tool_calls:
                    for tool_call in tool_calls:
                        self._raise_time_budget_if_exhausted(run.id, iteration)
                        coordination_receipt = record_intent_lock_coordination_denial(
                            self.store,
                            run=run,
                            policy=policy,
                            actor=f"runner:{runner_metadata.id}",
                            intent_lock=intent_lock,
                            phase=f"{step.phase}:tool",
                        )
                        if coordination_receipt is not None:
                            receipts.append(coordination_receipt)
                            denied_tool_receipt = coordination_receipt
                            break
                        side_effect = dispatch_tool_call_side_effect(
                            store=self.store,
                            policy=policy,
                            grants=active_grants,
                            tool_call=tool_call,
                            actor=f"runner:{runner_metadata.id}",
                            sandbox_config=step_context.get("local_process_sandbox"),
                        )
                        if side_effect is None:
                            continue
                        receipts.append(side_effect.receipt)
                        if side_effect.receipt.id not in receipt_ids:
                            receipt_ids.append(side_effect.receipt.id)
                        tool_messages.append(
                            attested_tool_message(
                                store=self.store,
                                task_id=task_id,
                                case_file_id=case_file_id,
                                tool_call=tool_call,
                                side_effect=side_effect,
                            )
                        )
                        if not side_effect.allowed:
                            denied_tool_receipt = side_effect.receipt
                            break

                if receipt_ids != result.receipt_ids:
                    result = result.model_copy(update={"receipt_ids": receipt_ids})
                capture = self.outputs.capture_step_result(
                    result,
                    proposal_specs=step.proposal_specs,
                )
                step_results.append(result)
                output_captures.append(capture)

                if denied_tool_receipt is not None:
                    run = self.runs.transition(
                        run.id,
                        RunTransition(
                            status="blocked",
                            phase="stop",
                            iteration=iteration,
                            receipt_id=denied_tool_receipt.id,
                            stop_reason=denied_tool_receipt.reason,
                            at=datetime.now(UTC),
                        ),
                    )
                    return LoopExecutionResult(run, step_results, output_captures, receipts)

                if result.status in {"blocked", "failed"}:
                    terminal_status: TaskRunStatus = (
                        "blocked" if result.status == "blocked" else "failed"
                    )
                    run = self.runs.transition(
                        run.id,
                        RunTransition(
                            status=terminal_status,
                            phase="stop",
                            iteration=iteration,
                            receipt_id=side_effect_receipt.id if side_effect_receipt else None,
                            stop_reason=result.summary,
                            at=datetime.now(UTC),
                        ),
                    )
                    return LoopExecutionResult(run, step_results, output_captures, receipts)

                if not tool_messages:
                    break
                message_history.extend(tool_messages)
                tool_round += 1

            run = self.runs.transition(
                run.id,
                RunTransition(
                    status="running",
                    phase=step.phase,
                    iteration=iteration,
                    receipt_id=side_effect_receipt.id if side_effect_receipt else None,
                    completed_step_key=step_key,
                    last_step_key=step_key,
                    at=datetime.now(UTC),
                ),
            )

        run = self.runs.transition(
            run.id,
            RunTransition(
                status="completed",
                phase="stop",
                stop_reason="loop completed",
                at=datetime.now(UTC),
            ),
        )
        return LoopExecutionResult(run, step_results, output_captures, receipts)

    def _raise_time_budget_if_exhausted(self, run_id: str, iteration: int) -> None:
        raise_time_budget_if_exhausted(
            runs=self.runs,
            run_id=run_id,
            iteration=iteration,
            error_type=LoopTimeBudgetExceededError,
        )

    def _raise_provider_budget_if_exhausted(self, run_id: str, iteration: int) -> None:
        raise_provider_budget_if_exhausted(
            runs=self.runs,
            run_id=run_id,
            iteration=iteration,
            error_type=LoopProviderBudgetExceededError,
        )

    def _completed_step_capture(
        self,
        run_id: str,
        step_key: str,
    ) -> RunOutputCapture | None:
        return completed_step_capture(
            self.store.list_run_outputs(),
            run_id=run_id,
            step_key=step_key,
        )
