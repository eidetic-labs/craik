"""Session portability CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from craik.cli import session_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.runtime.agents.session_portability import (
    export_agent_session,
    import_session_export,
    session_export_payload,
)
from craik.runtime.store import LocalStore


@session_app.command("export-portable")
def session_export_portable(
    session_id: Annotated[str, typer.Argument(help="Persistent session id to export.")],
) -> None:
    """Export one persistent session in portable v0.12.0 format."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
        if session is None:
            raise typer.BadParameter(f"unknown session: {session_id}")
        events = store.list_agent_session_events()
    finally:
        store.close()
    export = export_agent_session(session, events)
    typer.echo(json.dumps(session_export_payload(export), indent=2, sort_keys=True))


@session_app.command("import-portable")
def session_import_portable(
    path: Annotated[Path, typer.Option("--path", help="Craik or adjacent transcript JSON path.")],
) -> None:
    """Parse a portable session or adjacent transcript without executing tools."""
    try:
        export = import_session_export(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(session_export_payload(export), indent=2, sort_keys=True))
