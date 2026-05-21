"""Reference integration CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli import references_app
from craik.runtime.store import LocalStore


@references_app.command("list")
def references_list() -> None:
    """List reference integrations."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        integrations = store.list_reference_integrations()
    finally:
        store.close()
    typer.echo(json.dumps([_payload(item) for item in integrations], indent=2, sort_keys=True))


@references_app.command("verify")
def references_verify(
    integration_id: Annotated[str, typer.Argument(help="Reference integration id.")],
) -> None:
    """Verify that a reference integration is present and valid."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        integration = store.get_reference_integration(integration_id)
    finally:
        store.close()
    if integration is None:
        raise typer.BadParameter(f"unknown reference integration: {integration_id}")
    _print(integration)


def _payload(model: object) -> dict[str, object]:
    return model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined,no-any-return]


def _print(model: object) -> None:
    typer.echo(json.dumps(_payload(model), indent=2, sort_keys=True))
