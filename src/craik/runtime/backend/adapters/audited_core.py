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

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from craik.cli_run_support import fixture_shell_grant, provider_run_payload
from craik.runtime.backend import session
from craik.runtime.backend.adapters.base import strip_contract_envelopes
from craik.runtime.backend.events import (
    BackendEvent,
    Coalescer,
    EventSource,
    assistant_text_event,
    receipt_event,
    run_completed_event,
    run_started_event,
    tool_event,
)
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
from craik.runtime.providers.provider_transport import normalize_provider_family
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


# --- Typed emission (Task 5.5a) ---------------------------------------------
# These helpers derive the NEW typed event sequence from the SAME ``*CoreResult``
# the legacy emission layer derives the OLD events from. They are the typed
# counterpart of ``legacy_runs`` -- emission only; execution + persistence happen
# in the cores above. They live here (not a new ``adapters/`` file) because the
# ``adapters/`` package is at its 15-file cap.


def typed_claude_stream_sink(
    *,
    map_native: Callable[[dict[str, object]], BackendEvent | None],
    coalescer: Coalescer,
    sink: Callable[[BackendEvent], None],
) -> Callable[[BackendEvent], None]:
    """Return a ``stream`` sink for ``run_claude_code_core`` that emits TYPED events.

    ``run_claude_code_core`` (via ``_execute_claude_code_prompt``) delivers each
    native claude line to its ``stream`` callback as an OLD-shape
    ``BackendEvent`` whose ``data`` carries the native ``{"kind": ...}`` fields
    (``kind`` / ``text`` / ``tool`` / ``target`` / ``command`` / ...). This sink
    re-shapes each one through the adapter's ``map_native`` (the SAME mapper +
    ``Coalescer`` the Phase-4 fixture tests exercise): assistant-text snapshots
    are coalesced (and emitted once at flush by the caller), and tool / approval
    / receipt kinds are forwarded to ``sink`` as typed events. Non-canonical
    kinds map to ``None`` and are dropped.

    The returned callable is what the typed ``run()`` passes as the core's
    ``stream``; the caller flushes ``coalescer`` and emits the framing events
    AFTER the core returns (see :func:`claude_framing_events`).
    """

    def _on_native(old_event: BackendEvent) -> None:
        # The OLD event's ``data`` is a superset of the native dict the mapper
        # reads (the legacy ``claude_structured_event_to_backend_event`` copies
        # the native fields onto ``data``); pass it straight through.
        typed = map_native(old_event.data)
        if typed is not None:
            sink(typed)

    # ``coalescer`` is owned by the adapter and flushed by the caller; bound here
    # only so the signature documents the seam it cooperates with.
    _ = coalescer
    return _on_native


def claude_framing_events(
    core: ClaudeCoreResult,
    *,
    source: EventSource,
) -> Iterator[BackendEvent]:
    """Yield the TYPED framing events derived from a :class:`ClaudeCoreResult`.

    The native per-line events were already emitted DURING the core run via the
    typed stream sink; this derives only the framing the legacy layer derives
    after the fact -- ``run.started``, a ``receipt.created`` per persisted
    receipt id, and ``run.completed`` -- as canonical typed builders carrying the
    core's ``run_id`` / ``task_id`` / ``status``. Receipt posture mirrors the
    CLI exemplar (``execution="delegated-observed"``: the CLI ran the tool, craik
    authorized + observed it).
    """
    yield run_started_event(source=source, run_id=core.run_id, task_id=core.task_id)
    for receipt_id in core.receipt_ids:
        yield receipt_event(
            receipt_id=receipt_id,
            source=source,
            purpose="execution",
            execution="delegated-observed",
            mode="default",
            decision="allow",
            decided_by="operator",
            run_id=core.run_id,
            task_id=core.task_id,
        )
    yield run_completed_event(
        status=str(core.status),
        source=source,
        run_id=core.run_id,
        task_id=core.task_id,
    )


def provider_typed_events(
    core: ProviderCoreResult,
    *,
    source: EventSource,
) -> Iterator[BackendEvent]:
    """Yield the full TYPED event sequence derived from a :class:`ProviderCoreResult`.

    The provider core produces NO events during execution, so the whole sequence
    is derived after the fact from the structured result:

    * one coalesced ``assistant_text`` (the per-step ``text`` joined, contract
      envelopes stripped) when any step produced text;
    * a ``tool.used`` per native tool call across ``result.provider_results``;
    * ``run.started`` framing;
    * a ``receipt.created`` per persisted receipt id carrying ``execution=
      "craik"`` (craik ran the provider step itself);
    * ``run.output`` summarizing the run stop reason;
    * ``run.completed`` with the terminal status.

    ``source`` is the originating adapter's vendor token (e.g. ``"openai-api"``).
    ``run_provider_typed`` guards that this vendor agrees with
    ``core.provider_family`` BEFORE deriving events, so by the time this runs the
    token always matches ``core.provider_family``; ``execute_prompt`` (5.7)
    selects the adapter matching the active provider to keep the guard satisfied.
    """
    run_id = core.run_id
    task_id = core.task_id
    text = strip_contract_envelopes(
        " ".join(step.text for step in core.result.provider_results if step.text)
    )
    if text:
        yield assistant_text_event(text=text, source=source, run_id=run_id, task_id=task_id)
    for index, step in enumerate(core.result.provider_results, start=1):
        for call in step.tool_calls:
            if not isinstance(call, dict):
                continue
            tool = call.get("name") or call.get("tool") or call.get("type")
            tool_name = str(tool) if tool else "provider_tool"
            yield tool_event(
                tool=tool_name,
                source=source,
                target=tool_name,
                message=(
                    f"{step.provider_family} provider used `{tool_name}` during step {index}."
                ),
                run_id=run_id,
                task_id=task_id,
            )
    yield run_started_event(source=source, run_id=run_id, task_id=task_id)
    for receipt_id in core.receipt_ids:
        yield receipt_event(
            receipt_id=receipt_id,
            source=source,
            purpose="execution",
            execution="craik",
            mode="default",
            decision="allow",
            decided_by="operator",
            run_id=run_id,
            task_id=task_id,
        )
    # ``run.output`` requires a non-empty ``data.summary`` per the event
    # contract; fall back to the terminal status when the run carries no stop
    # reason so the typed event stays contract-valid.
    summary = core.result.run.stop_reason or str(core.status)
    yield BackendEvent(
        type="run.output",
        source=source,
        run_id=run_id,
        task_id=task_id,
        data={"summary": summary, "model": core.resolved_model},
    )
    yield run_completed_event(
        status=str(core.status),
        source=source,
        run_id=run_id,
        task_id=task_id,
    )


def run_provider_typed(
    *,
    prompt: str,
    env: dict[str, str] | None,
    source: EventSource,
    provider_source: session.PromptSource,
) -> Iterator[BackendEvent]:
    """Compose the provider core and yield its NEW TYPED event sequence.

    The single live API ``run()`` body shared by ``AnthropicAPI`` / ``GoogleAPI``
    / ``OpenAIAPI``: it runs + persists the audited provider run via
    ``run_provider_core`` (the SAME machinery the legacy provider layer uses),
    derives the typed events from the :class:`ProviderCoreResult`, persists the
    gateway-event-history artifact with the core's still-open ``store``, and
    closes that store exactly ONCE in a ``finally`` (leak-free), mirroring
    ``legacy_runs._legacy_provider_run``.

    ``source`` is the originating adapter's vendor token stamped on emitted
    events; ``provider_source`` is the operator ``PromptSource`` recorded on the
    created task. The adapter vendor (derived from ``source``) MUST agree with the
    core's resolved ``provider_family`` -- if it does not, this refuses to emit
    (raising ``ValueError``) rather than write a wrong-vendor audit record. The
    core's store is still closed exactly once on that raise path.
    """
    core = run_provider_core(prompt=prompt, env=env, source=provider_source)
    store = core.store
    try:
        # The adapter stamps its OWN vendor token (``<vendor>-api``) on every
        # emitted event while the core independently resolves the active
        # provider family from the env/model. If they disagree, emitting would
        # write a WRONG-VENDOR audit record (e.g. ``anthropic-api`` receipts over
        # an openai run). Refuse to emit on mismatch. ``normalize_provider_family``
        # collapses the legacy ``gemini`` alias to ``google`` so it still matches.
        # This raise happens AFTER the core ran, so the ``finally`` below still
        # closes the store exactly once (leak-free).
        vendor = source.split("-", 1)[0]
        resolved_family = core.provider_family
        if resolved_family is None or vendor != normalize_provider_family(resolved_family):
            raise ValueError(
                f"adapter vendor '{vendor}' does not match resolved provider family "
                f"'{core.provider_family}'; refusing to emit wrong-vendor receipts"
            )
        events = list(provider_typed_events(core, source=source))
        yield from events
        session._persist_gateway_event_history(core.payload, events, store=store)
    finally:
        store.close()


__all__ = [
    "ClaudeCoreResult",
    "ProviderCoreResult",
    "claude_framing_events",
    "provider_typed_events",
    "run_claude_code_core",
    "run_provider_core",
    "run_provider_typed",
    "typed_claude_stream_sink",
]
