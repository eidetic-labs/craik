"""Reference integration CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer

from craik.cli import references_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.cli_output import emit_command_result
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.store import LocalStore


@references_app.command("list")
@craik_command(payload_shape="card_list")
def references_list() -> CommandResult:
    """List reference integrations."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        integrations = store.list_reference_integrations()
    finally:
        store.close()
    result = CommandResult(
        payload=[_payload(item) for item in integrations],
        shape="card_list",
    )
    emit_command_result(result)
    return result


@references_app.command("verify")
@craik_command(payload_shape="card")
def references_verify(
    integration_id: Annotated[str, typer.Argument(help="Reference integration id.")],
) -> CommandResult:
    """Verify that a reference integration is present and valid."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        integration = store.get_reference_integration(integration_id)
    finally:
        store.close()
    if integration is None:
        raise typer.BadParameter(f"unknown reference integration: {integration_id}")
    result = CommandResult(payload=_payload(integration), shape="card")
    emit_command_result(result)
    return result


def _payload(model: object) -> dict[str, object]:
    return model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined,no-any-return]
