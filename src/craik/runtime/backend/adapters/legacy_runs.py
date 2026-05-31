"""Legacy ``execute_prompt`` run branches, extracted from ``session`` (Task 2.4).

These two helpers hold the byte-identical bodies of the legacy claude-code and
provider branches. They live in their own module purely to keep ``session`` under
the file-size guard; the adapters' ``_legacy_run`` methods bridge here.

Import direction is one-way: ``legacy_runs`` imports from ``session`` (for the
shared private helpers and the in-module provider selectors), and ``session``
must NOT import ``legacy_runs``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from craik.cli_run_support import fixture_shell_grant, provider_run_payload
from craik.runtime.backend import session
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.provider_events import (
    model_display_name,
    provider_family,
    provider_tool_call_events,
)
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.providers.provider_runner import ProviderBackedRunExecutor
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.tasks import create_task


def _legacy_claude_code_run(
    *,
    prompt: str,
    env: dict[str, str] | None,
    emit: Callable[[BackendEvent], None],
    events: list[BackendEvent],
    require_operator_approval: bool,
) -> session.BackendPromptResult:
    """Verbatim body of the legacy claude-code branch of ``execute_prompt``."""
    emit(BackendEvent(type="model.selected", data={"backend": "claude-code"}))
    emit(
        BackendEvent(
            type="run.working",
            data={"backend": "claude-code", "phase": "starting"},
        )
    )
    approval_required = require_operator_approval
    payload = session._execute_claude_code_prompt(
        prompt,
        env=env,
        stream=emit,
        require_operator_approval=approval_required,
    )
    run = payload.get("run")
    task = payload.get("task")
    run_id = run.get("id") if isinstance(run, dict) else None
    task_id = task.get("id") if isinstance(task, dict) else None
    emit(
        BackendEvent(
            type="run.started",
            run_id=run_id if isinstance(run_id, str) else None,
            task_id=task_id if isinstance(task_id, str) else None,
            data={"backend": "claude-code"},
        )
    )
    receipt_ids = payload.get("receipt_ids")
    for receipt_id in receipt_ids if isinstance(receipt_ids, list) else []:
        if isinstance(receipt_id, str):
            emit(
                BackendEvent(
                    type="receipt.created",
                    run_id=run_id if isinstance(run_id, str) else None,
                    task_id=task_id if isinstance(task_id, str) else None,
                    data={"receipt_id": receipt_id},
                )
            )
    status = payload.get("status")
    emit(
        BackendEvent(
            type="run.completed",
            run_id=run_id if isinstance(run_id, str) else None,
            task_id=task_id if isinstance(task_id, str) else None,
            data={"status": status, "backend": "claude-code"},
        )
    )
    session._persist_gateway_event_history(payload, events, env=env)
    return session.BackendPromptResult(payload=payload, events=events)


def _legacy_provider_run(
    *,
    prompt: str,
    env: dict[str, str] | None,
    emit: Callable[[BackendEvent], None],
    events: list[BackendEvent],
    source: session.PromptSource,
) -> session.BackendPromptResult:
    """Verbatim body of the legacy provider branch of ``execute_prompt``."""
    normalized_prompt = prompt
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        project = ProjectRegistry(store).add_project(Path.cwd())
        title = session._title_from_prompt(normalized_prompt)
        task = create_task(
            store,
            title=title,
            objective=normalized_prompt,
            project_id=project.id,
            requested_by=f"user:{source}",
            mode="implement",
            expected_outputs=["runner_step_result", "handoff"],
        )
        CaseFileAssembler(store).build(task.id)
        provider_id, model = session.active_provider_and_model(env)
        active_profile = session.active_model_profile(env)
        selected_provider_family = provider_family(provider_id)
        display_name = model_display_name(
            provider_id=provider_id,
            model=model,
            profile=active_profile,
        )
        emit(
            BackendEvent(
                type="model.selected",
                task_id=task.id,
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
                task_id=task.id,
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
                task_id=task.id,
                data={
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": model,
                    "message": f"{display_name} is preparing an audited provider run.",
                },
            )
        )
        result = ProviderBackedRunExecutor(store).execute(
            task_id=task.id,
            provider_id=provider_id,
            grants=[fixture_shell_grant(task.id)],
            live_enabled=session.live_provider_enabled(env),
            model=model,
            provider_options=active_profile.options if active_profile is not None else None,
        )
        resolved_model = result.provider_results[-1].model if result.provider_results else model
        emit(
            BackendEvent(
                type="run.started",
                run_id=result.run.id,
                task_id=task.id,
                data={
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": resolved_model,
                },
            )
        )
        for event in provider_tool_call_events(
            result,
            run_id=result.run.id,
            task_id=task.id,
        ):
            emit(event)
        emit(
            BackendEvent(
                type="run.progress",
                run_id=result.run.id,
                task_id=task.id,
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
        payload = provider_run_payload(result)
        payload["project"] = project.model_dump(mode="json", by_alias=True)
        payload["task"] = task.model_dump(mode="json", by_alias=True)
        if active_profile is not None:
            payload["model_profile"] = active_profile.as_dict()
        receipt_ids = payload.get("receipt_ids")
        for receipt_id in receipt_ids if isinstance(receipt_ids, list) else []:
            if isinstance(receipt_id, str):
                emit(
                    BackendEvent(
                        type="receipt.created",
                        run_id=result.run.id,
                        task_id=task.id,
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
                run_id=result.run.id,
                task_id=task.id,
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
                run_id=result.run.id,
                task_id=task.id,
                data={
                    "status": result.run.status,
                    "provider_id": provider_id,
                    "provider_family": selected_provider_family,
                    "model": resolved_model,
                },
            )
        )
        session._persist_gateway_event_history(payload, events, store=store)
        return session.BackendPromptResult(payload=payload, events=events)
    except Exception as error:
        emit(BackendEvent(type="error", data={"message": str(error)}))
        raise
    finally:
        store.close()
