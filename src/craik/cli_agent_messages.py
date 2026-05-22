"""Agent mailbox CLI commands."""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer

from craik.cli import agent_message_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.contracts.models import AgentMessageKind
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.mailbox import (
    AgentMessageAuthorizationError,
    AgentMessageNotFoundError,
    record_agent_message_received,
    send_agent_message,
)


@agent_message_app.command("send")
def agent_message_send(
    task_id: Annotated[str, typer.Option("--task-id", help="Task id for the message.")],
    from_agent: Annotated[str, typer.Option("--from-agent", help="Authenticated sender id.")],
    to_agent: Annotated[str, typer.Option("--to-agent", help="Recipient agent id.")],
    subject: Annotated[str, typer.Option("--subject", help="Message subject.")],
    body: Annotated[str, typer.Option("--body", help="Message body.")],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Sender run id used to authenticate from-agent."),
    ],
    kind: Annotated[str, typer.Option("--kind", help="Message kind.")] = "request",
    from_role_id: Annotated[
        str | None,
        typer.Option("--from-role-id", help="Sender role id."),
    ] = None,
    from_role_kind: Annotated[
        str | None,
        typer.Option("--from-role-kind", help="Sender role kind."),
    ] = None,
    to_role_id: Annotated[
        str | None,
        typer.Option("--to-role-id", help="Recipient role id."),
    ] = None,
    to_role_kind: Annotated[
        str | None,
        typer.Option("--to-role-kind", help="Recipient role kind."),
    ] = None,
    handoff_id: Annotated[
        str | None,
        typer.Option("--handoff-id", help="Related handoff id."),
    ] = None,
) -> None:
    """Send a receipt-backed message from one authenticated run/role to another agent."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        policy = generate_policy_envelope(task_id=task_id, actor=from_agent)
        message = send_agent_message(
            store,
            policy=policy,
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            subject=subject,
            body=body,
            kind=_message_kind(kind),
            from_role_id=from_role_id,
            from_role_kind=from_role_kind,
            to_role_id=to_role_id,
            to_role_kind=to_role_kind,
            run_id=run_id,
            handoff_id=handoff_id,
        )
    except (AgentMessageAuthorizationError, AgentMessageNotFoundError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(json.dumps(message.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@agent_message_app.command("receive")
def agent_message_receive(
    message_id: Annotated[str, typer.Argument(help="Message id to mark received.")],
    received_by: Annotated[str, typer.Option("--received-by", help="Receiving agent id.")],
) -> None:
    """Mark an agent mailbox message as received and append a receipt."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        message = store.get_agent_message(message_id)
        if message is None:
            raise AgentMessageNotFoundError(f"unknown agent message: {message_id}")
        policy = generate_policy_envelope(task_id=message.task_id, actor=received_by)
        received = record_agent_message_received(
            store,
            policy=policy,
            message_id=message_id,
            received_by=received_by,
        )
    except AgentMessageNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(
        json.dumps(received.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


def _message_kind(value: str) -> AgentMessageKind:
    if value not in {
        "request",
        "response",
        "status",
        "question",
        "answer",
        "decision",
        "handoff",
        "review",
    }:
        raise typer.BadParameter(f"unsupported message kind: {value}")
    return cast(AgentMessageKind, value)
