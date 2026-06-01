"""Emission-agnostic audited-execution cores (Task 5.4 / 5.5b).

Each core performs an audited run (store/task setup, execution, receipt
persistence, payload assembly) factored OUT of event emission, returning a
``*CoreResult`` an emission layer derives events from. The core never decides
event shapes.

* :func:`run_claude_code_core` -- the Claude Code subprocess; native events
  stream DURING the run via an injected ``stream`` sink (the only emission
  seam), framing derived by the caller from :class:`ClaudeCoreResult` after.
* :func:`run_provider_core` -- the ``ProviderBackedRunExecutor``; no events
  during the run, so the whole sequence is derived from
  :class:`ProviderCoreResult`. The still-open ``store`` is returned for the
  caller to persist gateway history with, then close.

The GENERIC vendor-CLI core (``gemini`` / ``codex``, Task 5.5b) -- the model of
``run_claude_code_core`` generalized to any ``argv`` -- lives in
``backend.cli.cli_audited`` (its own package because ``backend`` /
``backend/adapters`` are at the sibling-module layout cap); its subprocess pump
is ``sandbox.cli_stream``.

Import direction: this module imports from ``session`` for shared private
helpers; ``session`` must NOT import this module.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from craik.cli_run_support import fixture_shell_grant, provider_run_payload
from craik.runtime.backend import session
from craik.runtime.backend.adapters.base import (
    ReceiptPosture,
    RunContext,
    strip_contract_envelopes,
)
from craik.runtime.backend.events import (
    BackendEvent,
    Coalescer,
    EventSource,
    ReceiptDecidedBy,
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

    Carries everything an emission layer needs to derive the framing events. The
    native per-line stream events were delivered to the injected ``stream`` sink
    DURING execution, so they are not re-carried. ``receipt_ids`` are string-only
    in payload order; ``status`` is the terminal run status.
    """

    payload: dict[str, object]
    run_id: str | None
    task_id: str | None
    status: object
    receipt_ids: list[str]


@dataclass(frozen=True)
class ProviderCoreResult:
    """Structured result of an audited provider run, emission-agnostic.

    Carries everything an emission layer needs to derive every event (no events
    are produced during execution). The still-open ``store`` is returned so the
    caller can persist the gateway-event-history artifact with the same store the
    run used, then close it. ``provider_family`` is ``None`` when the provider id
    maps to no known family; ``receipt_ids`` are string-only in payload order.
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
# the legacy emission layer derives the OLD events from -- emission only;
# execution + persistence happen in the cores above. They live here (not a new
# ``adapters/`` file) because the ``adapters/`` package is at its 15-file cap.


def typed_claude_stream_sink(
    *,
    map_native: Callable[[dict[str, object]], BackendEvent | None],
    coalescer: Coalescer,
    sink: Callable[[BackendEvent], None],
) -> Callable[[BackendEvent], None]:
    """Return a ``stream`` sink for ``run_claude_code_core`` that emits TYPED events.

    Re-shapes each native claude line (delivered as an OLD-shape ``BackendEvent``
    whose ``data`` carries the native fields) through the adapter's
    ``map_native`` + ``Coalescer``: text snapshots are coalesced (flushed once by
    the caller), tool/approval/receipt kinds forward to ``sink``, non-canonical
    kinds drop. The caller flushes ``coalescer`` and emits framing AFTER the core
    returns (see :func:`claude_framing_events`).
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


def cli_observed_decided_by(require_operator_approval: bool) -> ReceiptDecidedBy:
    """Return the honest ``decided_by`` for a delegated-observed CLI receipt.

    Task 5.7 parity item C: an ``operator``-attributed receipt must persist ONLY
    when an operator actually decided -- i.e. a GATED run (live operator approval
    was requested + flows through the hook bridge). An ungated / auto run
    authored no operator decision, so it reflects the TRUE posture ``"bypass"``
    (the ungoverned/observe flag) rather than a falsely-attributed ``operator``.
    """
    return "operator" if require_operator_approval else "bypass"


def claude_framing_events(
    core: ClaudeCoreResult,
    *,
    source: EventSource,
    decided_by: ReceiptDecidedBy = "bypass",
) -> Iterator[BackendEvent]:
    """Yield the TYPED framing events derived from a :class:`ClaudeCoreResult`.

    The native per-line events were already emitted DURING the core run via the
    typed stream sink; this derives the framing -- ``run.started``, a
    ``receipt.created`` per persisted receipt id (``execution=
    "delegated-observed"``), and ``run.completed`` -- carrying the core's ids /
    status. ``decided_by`` carries the REAL governance attribution (parity item
    C): ``"operator"`` only for a gated run, else ``"bypass"`` (ungated/observe).
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
            decided_by=decided_by,
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
    is derived after the fact: one coalesced ``assistant_text`` (contract
    envelopes stripped) when any step produced text; a ``tool.used`` per native
    tool call; ``run.started``; a ``receipt.created`` per persisted receipt id
    (``execution="craik"``); ``run.output`` summarizing the stop reason;
    ``run.completed``. ``source`` is the adapter vendor token, guarded against
    ``core.provider_family`` by ``run_provider_typed`` before this runs.
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


class _ProviderAPIAdapter(Protocol):
    """The slice of an API adapter ``provider_api_run`` reads.

    The three API adapters (``AnthropicAPI`` / ``GoogleAPI`` / ``OpenAIAPI``)
    share an identical live ``run()`` body: stamp the vendor token from
    ``posture.source``, thread the ORIGINAL env + operator ``PromptSource``, and
    capture the audited payload onto ``last_payload``. This Protocol pins exactly
    those attributes so the shared wiring stays vendor-agnostic.
    """

    posture: ReceiptPosture
    original_env: dict[str, str] | None
    prompt_source: str
    last_payload: dict[str, object] | None


def provider_api_run(adapter: _ProviderAPIAdapter, ctx: RunContext) -> Iterator[BackendEvent]:
    """Yield the shared live API-adapter ``run()`` sequence for ``adapter``.

    The identical body the three API adapters' ``run()`` compose: run + persist
    via the audited provider core and yield the NEW TYPED event sequence through
    :func:`run_provider_typed`, stamping the adapter's vendor token
    (``posture.source``) on every event, threading the adapter's ORIGINAL env and
    operator ``PromptSource``, and capturing the audited payload onto
    ``adapter.last_payload`` (the ``on_payload`` seam ``execute_prompt`` reads).
    Behavior is identical to the former per-adapter bodies (same events, same
    payload capture, same vendor guard, same single store close).
    """

    def _capture_payload(payload: dict[str, object]) -> None:
        adapter.last_payload = payload

    yield from run_provider_typed(
        prompt=ctx.prompt,
        # The ORIGINAL env (possibly None), threaded like the legacy path.
        env=adapter.original_env,
        source=adapter.posture.source,
        provider_source=adapter.prompt_source,  # type: ignore[arg-type]
        on_payload=_capture_payload,
    )


def run_provider_typed(
    *,
    prompt: str,
    env: dict[str, str] | None,
    source: EventSource,
    provider_source: session.PromptSource,
    on_payload: Callable[[dict[str, object]], None] | None = None,
) -> Iterator[BackendEvent]:
    """Compose the provider core and yield its NEW TYPED event sequence.

    The live API ``run()`` body shared by ``AnthropicAPI`` / ``GoogleAPI`` /
    ``OpenAIAPI``: run + persist via ``run_provider_core``, derive typed events,
    persist gateway history with the core's still-open ``store``, and close it
    exactly ONCE in a ``finally``. ``source`` is the adapter vendor token;
    ``provider_source`` is the operator ``PromptSource`` on the task. If the
    adapter vendor disagrees with the resolved ``provider_family`` this refuses
    to emit (``ValueError``) rather than write a wrong-vendor record.

    ``on_payload`` is the OPTIONAL payload-capture seam the Task 5.7 cutover uses:
    after the core runs (and passes the vendor guard) the core's audited payload
    is handed to ``on_payload`` so ``execute_prompt`` can build a
    ``BackendPromptResult`` from a generator-shaped run(). It is invoked BEFORE
    the events are yielded, only on a non-mismatch run.
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
        if on_payload is not None:
            on_payload(core.payload)
        events = list(provider_typed_events(core, source=source))
        yield from events
        session._persist_gateway_event_history(core.payload, events, store=store)
    finally:
        store.close()


__all__ = [
    "ClaudeCoreResult",
    "ProviderCoreResult",
    "claude_framing_events",
    "cli_observed_decided_by",
    "provider_api_run",
    "provider_typed_events",
    "run_claude_code_core",
    "run_provider_core",
    "run_provider_typed",
    "typed_claude_stream_sink",
]
