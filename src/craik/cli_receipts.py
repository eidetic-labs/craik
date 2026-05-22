"""Receipts CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli_operator_auth import operator_identity_or_fail
from craik.runtime.store import LocalStore
from craik.runtime.work.receipts import ReceiptNotFoundError, ReceiptStore

receipts_app = typer.Typer(help="Inspect persisted capability receipts.")


@receipts_app.command("list")
def receipts_list(
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", help="Only include receipts for this task id."),
    ] = None,
    policy_id: Annotated[
        str | None,
        typer.Option("--policy-id", help="Only include receipts linked to this policy envelope."),
    ] = None,
    handoff_id: Annotated[
        str | None,
        typer.Option("--handoff-id", help="Only include receipts linked to this handoff."),
    ] = None,
) -> None:
    """Print persisted capability receipts as JSON."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        receipt_store = ReceiptStore(store)
        receipts = receipt_store.list_receipts(
            task_id=task_id,
            policy_id=policy_id,
            handoff_id=handoff_id,
        )
    finally:
        store.close()

    payload = [receipt.model_dump(mode="json", by_alias=True) for receipt in receipts]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@receipts_app.command("show")
def receipts_show(receipt_id: str) -> None:
    """Print one capability receipt by id as JSON."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        receipt_store = ReceiptStore(store)
        receipt = receipt_store.require_receipt(receipt_id)
    except ReceiptNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(json.dumps(receipt.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))
