"""Generic audited vendor-CLI core + typed-emission composer (Task 5.5b).

``run_cli_core`` generalizes ``audited_core.run_claude_code_core``'s structure to
ANY ``argv``-launched CLI (``gemini`` / ``codex``): create the audited task/run
in ``LocalStore``, spawn the REAL subprocess via ``sandbox.cli_stream`` streaming
native lines to an injected sink DURING the run, persist the run + a single
run-level delegated-observed ``CapabilityReceipt`` + a ``RunOutput``, and return
a :class:`CliCoreResult`. ``run_cli_typed`` is the shared live ``run()`` body the
``GoogleCLI`` / ``OpenAICLI`` adapters compose: it drives the core with each
adapter's native mapper + ``Coalescer`` and yields the typed event sequence.

The execution + persistence here are emission-agnostic; the receipt POSTURE
stamped on emitted events is owned by each adapter's ``map_native_event``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from craik.cli_run_support import fixture_shell_grant
from craik.contracts.models import CapabilityReceipt, ReceiptResult, RunOutput
from craik.runtime.backend import session
from craik.runtime.backend.events import (
    BackendEvent,
    Coalescer,
    EventSource,
    run_completed_event,
    run_started_event,
)
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.projects.prompts import PromptCompiler
from craik.runtime.sandbox.cli_stream import CliStreamOutcome, stream_cli_subprocess
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.runs import RunTransition, TaskRunManager
from craik.runtime.work.tasks import create_task


@dataclass(frozen=True)
class CliCoreResult:
    """Structured result of an audited vendor-CLI run, emission-agnostic.

    The CLI counterpart of ``ClaudeCoreResult``: native per-line events streamed
    DURING the run via the injected ``stream`` sink, so they are not re-carried.
    ``status`` is the terminal run status (``completed`` / ``failed`` /
    ``interrupted`` -- a subprocess failure is a completed-with-error run, never a
    crash). ``receipt_ids`` is the single run-level delegated-observed receipt id.
    """

    payload: dict[str, object]
    run_id: str | None
    task_id: str | None
    status: object
    receipt_ids: list[str]


def run_cli_core(
    *,
    prompt: str,
    env: dict[str, str] | None,
    argv: list[str],
    spawn_env: dict[str, str],
    vendor: str,
    stream: Callable[[str], None],
) -> CliCoreResult:
    """Run an audited vendor-CLI subprocess and return its structured result.

    Creates the task/run in ``LocalStore`` (the audited record), spawns the REAL
    subprocess via ``stream_cli_subprocess`` (argv list only, never a shell)
    feeding each native stdout line to ``stream`` AS IT ARRIVES, bounds the wait
    so it never hangs, and treats any nonzero exit / no output / timeout /
    interrupt as a COMPLETED-WITH-ERROR run.

    Receipt persistence (observe-only design): these CLI runs are
    ``delegated-observed`` -- the vendor CLI authored + ran the tool calls; craik
    OBSERVED them. craik authored no per-tool decision, so rather than mint
    synthetic per-tool receipts this persists ONE run-level ``CapabilityReceipt``
    (``capability="<vendor>.cli.execute"``) attesting the observed run, reusing
    the SAME store/receipt machinery the claude core uses (``store.put_receipt``
    + a ``RunOutput``). The adapter persists the gateway-event-history artifact
    separately (``_persist_gateway_event_history``), mirroring the claude /
    provider paths.
    """
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        project = ProjectRegistry(store).add_project(Path.cwd())
        task = create_task(
            store,
            title=session._title_from_prompt(prompt),
            objective=prompt,
            project_id=project.id,
            requested_by="user:tui",
            mode="implement",
            expected_outputs=["runner_step_result", "handoff"],
        )
        store.put_capability_grant(fixture_shell_grant(task.id))
        case_file = CaseFileAssembler(store).build(task.id)
        compiled = PromptCompiler(store).compile(
            task.id,
            runner_id=vendor,
            expected_output_schemas=["craik.runner_step_result", "craik.handoff"],
        )
        manager = TaskRunManager(store)
        run = manager.create(
            task_id=task.id,
            case_file_id=case_file.id,
            policy_envelope_id=compiled.policy_envelope_id,
            runner_id=vendor,
            runner_mode="live",
            runner_metadata=[
                {"runner_id": vendor, "backend": f"{vendor}-cli", "execution_mode": "local-cli"}
            ],
        )
        manager.transition(
            run.id,
            RunTransition(status="running", phase="act", iteration=1, last_step_key=vendor),
        )
        outcome = stream_cli_subprocess(argv, spawn_env, on_line=stream)
        receipt = _put_cli_observed_receipt(store, task.id, run.id, vendor=vendor, outcome=outcome)
        store.put_run_output(
            RunOutput(
                id=f"runout_{run.id.removeprefix('run_')}_{vendor}_cli",
                run_id=run.id,
                step_result_id=f"runner_step_result_{run.id}_{vendor}_cli",
                task_id=task.id,
                phase="act",
                summary=(outcome.error or "Vendor CLI run completed.")[:240],
                observed_output={
                    "backend": f"{vendor}-cli",
                    "execution": "delegated-observed",
                    "returncode": outcome.returncode,
                    "raw_stream_events": outcome.lines,
                },
                diagnostics=[outcome.error] if outcome.error else [],
                receipt_ids=[receipt.id],
                artifacts=[compiled.id],
                created_at=datetime.now(UTC),
            )
        )
        final = manager.transition(
            run.id,
            RunTransition(
                status=outcome.status,  # type: ignore[arg-type]
                phase="stop",
                receipt_id=receipt.id,
                stop_reason=outcome.error or "Vendor CLI run completed.",
                completed_step_key=vendor if outcome.status == "completed" else None,
            ),
        )
        final = store.get_task_run(final.id) or final
        payload: dict[str, object] = {
            "schema": "craik.cli_run_execution",
            "version": "0.1.0",
            "status": final.status,
            "project": project.model_dump(mode="json", by_alias=True),
            "task": task.model_dump(mode="json", by_alias=True),
            "run": final.model_dump(mode="json", by_alias=True),
            "receipt_ids": [receipt.id],
            "backend": f"{vendor}-cli",
        }
        return CliCoreResult(
            payload=payload,
            run_id=final.id,
            task_id=task.id,
            status=final.status,
            receipt_ids=[receipt.id],
        )
    finally:
        store.close()


def _put_cli_observed_receipt(
    store: LocalStore,
    task_id: str,
    run_id: str,
    *,
    vendor: str,
    outcome: CliStreamOutcome,
) -> CapabilityReceipt:
    """Persist the single run-level delegated-observed receipt for a CLI run."""
    status: object = "passed" if outcome.status == "completed" else "failed"
    return store.put_receipt(
        CapabilityReceipt(
            id=f"receipt_{run_id.removeprefix('run_')}_{vendor}_cli",
            task_id=task_id,
            actor=f"runner:{vendor}-cli",
            capability=f"{vendor}.cli.execute",
            target=str(Path.cwd()),
            policy_profile="trusted-local",
            reason=f"Observe a delegated audited run through the local {vendor} CLI.",
            result=ReceiptResult(
                status=status,  # type: ignore[arg-type]
                summary=(outcome.error or "Vendor CLI run completed.")[:240],
                metadata={
                    "backend": f"{vendor}-cli",
                    "execution": "delegated-observed",
                    "returncode": outcome.returncode,
                },
            ),
            created_at=datetime.now(UTC),
        )
    )


def cli_framing_events(
    core: CliCoreResult,
    *,
    source: EventSource,
) -> Iterator[BackendEvent]:
    """Yield TYPED framing for a CLI run: ``run.started`` then ``run.completed``.

    The per-line ``tool.used`` / ``receipt.created`` / coalesced ``assistant_text``
    events were already produced via the adapter's ``map_native_event`` during the
    run; this adds only the run brackets carrying the core ids / terminal status.
    """
    yield run_started_event(source=source, run_id=core.run_id, task_id=core.task_id)
    yield run_completed_event(
        status=str(core.status),
        source=source,
        run_id=core.run_id,
        task_id=core.task_id,
    )


def run_cli_typed(
    *,
    prompt: str,
    env: dict[str, str] | None,
    argv: list[str],
    spawn_env: dict[str, str],
    vendor: str,
    source: EventSource,
    map_native: Callable[[dict[str, object]], BackendEvent | None],
    coalescer: Coalescer,
) -> Iterator[BackendEvent]:
    """Compose the CLI core and yield the adapter's NEW TYPED event sequence.

    The live CLI ``run()`` body shared by ``GoogleCLI`` / ``OpenAICLI``: it runs +
    persists the audited CLI run via :func:`run_cli_core`, mapping each native
    stdout line through the adapter's ``map_native`` + ``Coalescer`` AS IT ARRIVES
    (text snapshots coalesce, ``tool.used`` / ``receipt.created`` collect). After
    the core returns it yields the coalesced ``assistant_text`` (if any), the
    collected per-line events in arrival order, then the run framing, and persists
    the gateway-event-history artifact. A subprocess failure still yields a clean
    framed sequence ending in ``run.completed`` (status ``failed`` /
    ``interrupted``).
    """
    collected: list[BackendEvent] = []

    def _on_line(line: str) -> None:
        try:
            native = json.loads(line)
        except (ValueError, TypeError):
            return
        if not isinstance(native, dict):
            return
        event = map_native(native)
        if event is not None:
            collected.append(event)

    core = run_cli_core(
        prompt=prompt,
        env=env,
        argv=argv,
        spawn_env=spawn_env,
        vendor=vendor,
        stream=_on_line,
    )
    events: list[BackendEvent] = []
    flushed = coalescer.flush(None, source=source)
    if flushed is not None:
        events.append(flushed)
    events.extend(collected)
    events.extend(cli_framing_events(core, source=source))
    yield from events
    session._persist_gateway_event_history(core.payload, events, env=env)


__all__ = [
    "CliCoreResult",
    "cli_framing_events",
    "run_cli_core",
    "run_cli_typed",
]
