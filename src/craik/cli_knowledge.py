"""v0.5 runtime knowledge capture CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli import knowledge_app
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.store import LocalStore
from craik.runtime.work.context_debt import resolve_context_debt
from craik.runtime.work.known_traps import record_known_trap, record_negative_knowledge
from craik.runtime.work.scratchpad import (
    fulfill_context_request,
    record_unknown,
    request_context,
    resolve_unknown,
    write_scratchpad_record,
)


@knowledge_app.command("scratchpad")
def knowledge_scratchpad(
    task_id: Annotated[str, typer.Argument(help="Task id.")],
    note: Annotated[str, typer.Option("--note", help="Temporary note to persist.")],
    project_id: Annotated[str | None, typer.Option("--project", help="Project id.")] = None,
    evidence_id: Annotated[
        list[str] | None,
        typer.Option("--evidence-id", help="Evidence id. May be repeated."),
    ] = None,
) -> None:
    """Persist an expiring scratchpad note."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = write_scratchpad_record(
            store,
            task_id=task_id,
            project_id=project_id,
            owner=_operator_identity(),
            note=note,
            evidence_ids=evidence_id,
        )
    finally:
        store.close()
    _print(record)


@knowledge_app.command("unknown")
def knowledge_unknown(
    task_id: Annotated[str, typer.Argument(help="Task id.")],
    question: Annotated[str, typer.Option("--question", help="Unknown question.")],
    next_action: Annotated[str, typer.Option("--next-action", help="Action needed.")],
    needed_resolution: Annotated[
        str,
        typer.Option("--needed-resolution", help="Resolution source, such as user_input."),
    ] = "user_input",
    project_id: Annotated[str | None, typer.Option("--project", help="Project id.")] = None,
    evidence_id: Annotated[
        list[str] | None,
        typer.Option("--evidence-id", help="Evidence id. May be repeated."),
    ] = None,
) -> None:
    """Persist an unresolved unknown."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = record_unknown(
            store,
            task_id=task_id,
            project_id=project_id,
            owner=_operator_identity(),
            question=question,
            next_action=next_action,
            needed_resolution=needed_resolution,
            evidence_ids=evidence_id,
        )
    finally:
        store.close()
    _print(record)


@knowledge_app.command("context-request")
def knowledge_context_request(
    task_id: Annotated[str, typer.Argument(help="Task id.")],
    question: Annotated[str, typer.Option("--question", help="Requested context.")],
    needed_for: Annotated[str, typer.Option("--needed-for", help="Why this context is needed.")],
    kind: Annotated[str, typer.Option("--kind", help="Context source kind.")] = "user_input",
    project_id: Annotated[str | None, typer.Option("--project", help="Project id.")] = None,
    unknown_id: Annotated[
        str | None,
        typer.Option("--unknown-id", help="Linked unknown id."),
    ] = None,
) -> None:
    """Persist a context request that blocks continuation until fulfilled."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = request_context(
            store,
            task_id=task_id,
            project_id=project_id,
            requester=_operator_identity(),
            kind=kind,
            question=question,
            needed_for=needed_for,
            unknown_id=unknown_id,
        )
    finally:
        store.close()
    _print(record)


@knowledge_app.command("resolve-unknown")
def knowledge_resolve_unknown(
    unknown_id: Annotated[str, typer.Argument(help="Unknown record id.")],
    answer: Annotated[str, typer.Option("--answer", help="Resolution answer.")],
) -> None:
    """Resolve an unknown and link the operator receipt."""
    operator = _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = resolve_unknown(
            store,
            unknown_id,
            answer=answer,
            resolved_by=operator,
        )
    finally:
        store.close()
    _print(record)


@knowledge_app.command("fulfill-context-request")
def knowledge_fulfill_context_request(
    request_id: Annotated[str, typer.Argument(help="Context request id.")],
) -> None:
    """Fulfill a context request and link the operator receipt."""
    operator = _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = fulfill_context_request(
            store,
            request_id,
            fulfilled_by=operator,
        )
    finally:
        store.close()
    _print(record)


@knowledge_app.command("resolve-context-debt")
def knowledge_resolve_context_debt(
    debt_id: Annotated[str, typer.Argument(help="Context debt record id.")],
    summary: Annotated[
        str | None,
        typer.Option("--summary", help="Resolution summary."),
    ] = None,
) -> None:
    """Resolve a context debt record and link the operator receipt."""
    operator = _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = resolve_context_debt(
            store,
            debt_id,
            resolved_by=operator,
            summary=summary,
        )
    finally:
        store.close()
    _print(record)


@knowledge_app.command("trap")
def knowledge_trap(
    kind: Annotated[str, typer.Option("--kind", help="Trap kind.")],
    statement: Annotated[str, typer.Option("--statement", help="Trap statement.")],
    avoidance: Annotated[str, typer.Option("--avoidance", help="Avoidance guidance.")],
    evidence_id: Annotated[
        list[str],
        typer.Option("--evidence-id", help="Evidence id. May be repeated."),
    ],
    project_id: Annotated[str | None, typer.Option("--project", help="Project id.")] = None,
    task_id: Annotated[str | None, typer.Option("--task", help="Task id.")] = None,
) -> None:
    """Persist an evidence-backed known trap."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = record_known_trap(
            store,
            kind=kind,
            statement=statement,
            avoidance=avoidance,
            evidence_ids=evidence_id,
            project_id=project_id,
            task_id=task_id,
        )
    finally:
        store.close()
    _print(record)


@knowledge_app.command("negative")
def knowledge_negative(
    statement: Annotated[str, typer.Option("--statement", help="Negative knowledge statement.")],
    scope: Annotated[str, typer.Option("--scope", help="Scope of the assertion.")],
    evidence_id: Annotated[
        list[str],
        typer.Option("--evidence-id", help="Evidence id. May be repeated."),
    ],
    trust_class: Annotated[str, typer.Option("--trust-class", help="Trust class.")] = "observed",
    project_id: Annotated[str | None, typer.Option("--project", help="Project id.")] = None,
    task_id: Annotated[str | None, typer.Option("--task", help="Task id.")] = None,
    contradicted_fact: Annotated[
        str | None,
        typer.Option("--contradicted-fact", help="Existing positive assertion contradicted."),
    ] = None,
) -> None:
    """Persist evidence-backed negative knowledge."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        record = record_negative_knowledge(
            store,
            statement=statement,
            scope=scope,
            trust_class=trust_class,
            evidence_ids=evidence_id,
            project_id=project_id,
            task_id=task_id,
            contradicted_fact=contradicted_fact,
        )
    finally:
        store.close()
    _print(record)


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik auth login") from None
    return session.subject


def _print(model: object) -> None:
    payload = model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
