"""Legacy ``execute_prompt`` run branches, extracted from ``session`` (Task 2.4).

These two helpers hold the EMISSION layer of the legacy claude-code and provider
branches. The audited run itself (execute + receipt persistence + payload
assembly) now lives in the emission-agnostic cores in ``audited_core``; these
helpers call a core, then emit the (old-shape) events the legacy path has always
emitted -- derived from the core's structured result -- persist history, and
return the same :class:`~craik.runtime.backend.session.BackendPromptResult`.
Behavior is byte-identical to the pre-extraction bodies.

Import direction is one-way: ``legacy_runs`` imports from ``session`` (for the
shared private helpers) and from ``audited_core``; ``session`` must NOT import
either.
"""

from __future__ import annotations

from collections.abc import Callable

from craik.runtime.backend import session
from craik.runtime.backend.adapters.audited_core import (
    run_claude_code_core,
    run_provider_core,
)
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.provider_events import (
    provider_tool_call_events,
)


def _legacy_claude_code_run(
    *,
    prompt: str,
    env: dict[str, str] | None,
    emit: Callable[[BackendEvent], None],
    events: list[BackendEvent],
    require_operator_approval: bool,
) -> session.BackendPromptResult:
    """Emit the legacy claude-code events around the audited claude-code core."""
    emit(BackendEvent(type="model.selected", data={"backend": "claude-code"}))
    emit(
        BackendEvent(
            type="run.working",
            data={"backend": "claude-code", "phase": "starting"},
        )
    )
    # The native per-line claude stream events are emitted DURING the core run
    # via this same ``emit`` sink (preserving today's interleaving exactly).
    core = run_claude_code_core(
        prompt=prompt,
        env=env,
        require_operator_approval=require_operator_approval,
        stream=emit,
    )
    run_id = core.run_id
    task_id = core.task_id
    emit(
        BackendEvent(
            type="run.started",
            run_id=run_id,
            task_id=task_id,
            data={"backend": "claude-code"},
        )
    )
    for receipt_id in core.receipt_ids:
        emit(
            BackendEvent(
                type="receipt.created",
                run_id=run_id,
                task_id=task_id,
                data={"receipt_id": receipt_id},
            )
        )
    emit(
        BackendEvent(
            type="run.completed",
            run_id=run_id,
            task_id=task_id,
            data={"status": core.status, "backend": "claude-code"},
        )
    )
    session._persist_gateway_event_history(core.payload, events, env=env)
    return session.BackendPromptResult(payload=core.payload, events=events)


def _legacy_provider_run(
    *,
    prompt: str,
    env: dict[str, str] | None,
    emit: Callable[[BackendEvent], None],
    events: list[BackendEvent],
    source: session.PromptSource,
) -> session.BackendPromptResult:
    """Emit the legacy provider events around the audited provider core."""
    try:
        core = run_provider_core(prompt=prompt, env=env, source=source)
    except Exception as error:
        emit(BackendEvent(type="error", data={"message": str(error)}))
        raise
    store = core.store
    try:
        result = core.result
        provider_id = core.provider_id
        selected_provider_family = core.provider_family
        model = core.model
        resolved_model = core.resolved_model
        display_name = core.display_name
        active_profile = core.active_profile
        run_id = core.run_id
        task_id = core.task_id
        emit(
            BackendEvent(
                type="model.selected",
                task_id=task_id,
                data={
                    "backend": "provider",
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": model,
                    "display_name": display_name,
                    "profile": active_profile.as_dict() if active_profile is not None else None,
                    "live_enabled": session.live_provider_enabled(env),
                },
            )
        )
        emit(
            BackendEvent(
                type="run.working",
                task_id=task_id,
                data={
                    "backend": "provider",
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": model,
                    "phase": "thinking",
                },
            )
        )
        emit(
            BackendEvent(
                type="run.progress",
                task_id=task_id,
                data={
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": model,
                    "message": f"{display_name} is preparing an audited provider run.",
                },
            )
        )
        emit(
            BackendEvent(
                type="run.started",
                run_id=run_id,
                task_id=task_id,
                data={
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": resolved_model,
                },
            )
        )
        for event in provider_tool_call_events(
            result,
            run_id=run_id,
            task_id=task_id,
        ):
            emit(event)
        emit(
            BackendEvent(
                type="run.progress",
                run_id=run_id,
                task_id=task_id,
                data={
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": resolved_model,
                    "message": (
                        f"{display_name} returned {len(result.provider_results)} "
                        "provider step result(s)."
                    ),
                },
            )
        )
        for receipt_id in core.receipt_ids:
            emit(
                BackendEvent(
                    type="receipt.created",
                    run_id=run_id,
                    task_id=task_id,
                    data={
                        "receipt_id": receipt_id,
                        "provider_id": provider_id,
                        "provider_family": selected_provider_family,
                    },
                )
            )
        emit(
            BackendEvent(
                type="run.output",
                run_id=run_id,
                task_id=task_id,
                data={
                    "summary": result.run.stop_reason,
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": resolved_model,
                },
            )
        )
        emit(
            BackendEvent(
                type="run.completed",
                run_id=run_id,
                task_id=task_id,
                data={
                    "status": core.status,
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": resolved_model,
                },
            )
        )
        session._persist_gateway_event_history(core.payload, events, store=store)
        return session.BackendPromptResult(payload=core.payload, events=events)
    except Exception as error:
        emit(BackendEvent(type="error", data={"message": str(error)}))
        raise
    finally:
        store.close()
