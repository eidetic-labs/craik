"""Emission-agnostic audited-execution cores extracted from ``legacy_runs`` (Task 5.4).

This module holds the *core* of the two legacy run paths -- the audited run
itself (store/task setup, execution via the claude subprocess / the
``ProviderBackedRunExecutor``, receipt persistence, and payload assembly) --
factored OUT of event emission. Each core returns a structured ``*CoreResult``
carrying everything an emission layer needs to derive events (ids, status,
receipt ids, the native claude stream / provider step results, the assembled
payload); the core itself NEVER decides event shapes.

Two cores exist because the two paths *execute* differently:

* :func:`run_claude_code_core` drives the Claude Code subprocess. Its native
  events are produced DURING execution (the subprocess streams stream-json
  lines), so the core takes an injected ``stream`` sink for those native events.
  That sink is the ONLY emission seam the core touches, and it is supplied by
  the caller -- the legacy layer feeds it the old-shape mapper, a later
  ``run()`` can feed it a typed mapper. The framing events
  (model.selected / run.working / run.started / receipt.created / run.completed)
  are derived by the caller from :class:`ClaudeCoreResult` *after* the core
  returns.
* :func:`run_provider_core` drives the ``ProviderBackedRunExecutor``. Provider
  execution does not stream during the run, so EVERY event (framing + tool-call
  + receipt + output) is derivable from :class:`ProviderCoreResult` after the
  fact; the core takes no sink at all. Because the gateway-event-history
  artifact must be persisted with the SAME open store the run used, the core
  returns the still-open ``store`` and the caller is responsible for closing it
  (the legacy layer does so in a ``finally``).

Import direction matches ``legacy_runs``: this module imports from ``session``
for the shared private helpers; ``session`` must NOT import this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from craik.cli_run_support import fixture_shell_grant, provider_run_payload
from craik.runtime.backend import session
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.provider_events import (
    model_display_name,
    provider_family,
)
from craik.runtime.modeling import ModelProfile
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.providers.provider_runner import (
    ProviderBackedRunExecutor,
    ProviderBackedRunResult,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.tasks import create_task


@dataclass(frozen=True)
class ClaudeCoreResult:
    """Structured result of an audited claude-code run, emission-agnostic.

    Carries everything an emission layer needs to derive the framing events for
    a claude-code run. The native per-line stream events were already delivered
    to the injected ``stream`` sink DURING execution (they cannot be replayed
    from a structured snapshot), so they are not re-carried here.

    Attributes:
        payload: The assembled run payload (``execute_claude_code_run`` output).
        run_id: The audited run id, if the payload carried a ``run.id`` string.
        task_id: The audited task id, if the payload carried a ``task.id`` string.
        status: The terminal run status from the payload, if any.
        receipt_ids: The persisted receipt ids (string-only), in payload order.
    """

    payload: dict[str, object]
    run_id: str | None
    task_id: str | None
    status: object
    receipt_ids: list[str]


@dataclass(frozen=True)
class ProviderCoreResult:
    """Structured result of an audited provider run, emission-agnostic.

    Carries everything an emission layer needs to derive every event for a
    provider run (no events are produced during execution). The still-open
    ``store`` is returned so the caller can persist the gateway-event-history
    artifact with the same store the run used, then close it.

    Attributes:
        payload: The assembled provider run payload (project/task/profile merged).
        result: The raw ``ProviderBackedRunResult`` (run, provider step results).
        store: The OPEN store the run used; the caller MUST close it.
        provider_id: The selected provider id.
        provider_family: The normalized provider family for the selected provider
            (``None`` when the provider id maps to no known family).
        model: The originally selected model (may be ``None``).
        resolved_model: The model resolved from the last provider step result.
        display_name: The operator-facing model display name.
        active_profile: The active model profile, if any.
        receipt_ids: The persisted receipt ids (string-only), in payload order.
        status: The terminal run status.
        run_id: The audited run id.
        task_id: The audited task id (the created task's id).
    """

    payload: dict[str, object]
    result: ProviderBackedRunResult
    store: LocalStore
    provider_id: str
    provider_family: str | None
    model: str | None
    resolved_model: str | None
    display_name: str
    active_profile: ModelProfile | None
    receipt_ids: list[str]
    status: object
    run_id: str
    task_id: str


def _payload_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string_receipt_ids(payload: dict[str, object]) -> list[str]:
    receipt_ids = payload.get("receipt_ids")
    if not isinstance(receipt_ids, list):
        return []
    return [receipt_id for receipt_id in receipt_ids if isinstance(receipt_id, str)]


def run_claude_code_core(
    *,
    prompt: str,
    env: dict[str, str] | None,
    require_operator_approval: bool,
    stream: Callable[[BackendEvent], None] | None,
) -> ClaudeCoreResult:
    """Run the audited claude-code path and return its structured result.

    Performs the audited run (claude subprocess + receipt persistence + payload
    assembly) and returns the structured ids/status/receipt-ids/payload. The
    native per-line claude stream events are delivered to ``stream`` DURING the
    run (that is the only emission seam, and it is the caller's to define); the
    framing events are derived by the caller from the returned result. NO
    framing event is emitted here.
    """
    payload = session._execute_claude_code_prompt(
        prompt,
        env=env,
        stream=stream,
        require_operator_approval=require_operator_approval,
    )
    run = payload.get("run")
    task = payload.get("task")
    run_id = _payload_str(run.get("id")) if isinstance(run, dict) else None
    task_id = _payload_str(task.get("id")) if isinstance(task, dict) else None
    return ClaudeCoreResult(
        payload=payload,
        run_id=run_id,
        task_id=task_id,
        status=payload.get("status"),
        receipt_ids=_string_receipt_ids(payload),
    )


def run_provider_core(
    *,
    prompt: str,
    env: dict[str, str] | None,
    source: session.PromptSource,
) -> ProviderCoreResult:
    """Run the audited provider path and return its structured result.

    Performs the audited run (store/task/case-file setup + the
    ``ProviderBackedRunExecutor`` + receipt persistence + payload assembly) and
    returns the structured result the emission layer derives every event from.
    NO event is emitted here. The returned ``store`` is left OPEN so the caller
    can persist the gateway-event-history artifact with it and then close it;
    on failure the store is closed before the exception propagates.
    """
    store = LocalStore.from_env(env)
    store_open = True
    try:
        store.initialize()
        project = ProjectRegistry(store).add_project(Path.cwd())
        title = session._title_from_prompt(prompt)
        task = create_task(
            store,
            title=title,
            objective=prompt,
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
        result = ProviderBackedRunExecutor(store).execute(
            task_id=task.id,
            provider_id=provider_id,
            grants=[fixture_shell_grant(task.id)],
            live_enabled=session.live_provider_enabled(env),
            model=model,
            provider_options=active_profile.options if active_profile is not None else None,
        )
        resolved_model = result.provider_results[-1].model if result.provider_results else model
        payload = provider_run_payload(result)
        payload["project"] = project.model_dump(mode="json", by_alias=True)
        payload["task"] = task.model_dump(mode="json", by_alias=True)
        if active_profile is not None:
            payload["model_profile"] = active_profile.as_dict()
        # Ownership of ``store`` transfers to the caller (it must close it after
        # persisting gateway history). Keep it open past this point.
        store_open = False
        return ProviderCoreResult(
            payload=payload,
            result=result,
            store=store,
            provider_id=provider_id,
            provider_family=selected_provider_family,
            model=model,
            resolved_model=resolved_model,
            display_name=display_name,
            active_profile=active_profile,
            receipt_ids=_string_receipt_ids(payload),
            status=result.run.status,
            run_id=result.run.id,
            task_id=task.id,
        )
    finally:
        if store_open:
            store.close()


__all__ = [
    "ClaudeCoreResult",
    "ProviderCoreResult",
    "run_claude_code_core",
    "run_provider_core",
]
