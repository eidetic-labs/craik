"""Receipts CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from craik.cli_operator_auth import operator_identity_or_fail
from craik.runtime.store import LocalStore
from craik.runtime.work.receipts import ReceiptNotFoundError, ReceiptStore
from craik.tools.receipt_verifier import verify_receipt_bytes, verify_receipt_file

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


@receipts_app.command("verify")
def receipts_verify(
    path: Annotated[
        str,
        typer.Argument(help="Receipt JSON path, or '-' to read from stdin."),
    ],
    public_key: Annotated[
        Path | None,
        typer.Option("--public-key", help="HMAC key material path for verification."),
    ] = None,
    auto_discover: Annotated[
        bool,
        typer.Option("--auto-discover", help="Discover the local Craik HMAC key from CRAIK_HOME."),
    ] = False,
    side_log_base: Annotated[
        Path | None,
        typer.Option("--side-log-base", help="Directory containing shell side-log files."),
    ] = None,
) -> None:
    """Verify a receipt JSON file without trusting the producing runtime."""
    try:
        if path == "-":
            result = verify_receipt_bytes(
                sys.stdin.buffer.read(),
                public_key_path=public_key,
                auto_discover=auto_discover,
                side_log_base=side_log_base,
            )
        else:
            result = verify_receipt_file(
                path,
                public_key_path=public_key,
                auto_discover=auto_discover,
                side_log_base=side_log_base,
            )
    except OSError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    if not result.passed:
        raise typer.Exit(1)
