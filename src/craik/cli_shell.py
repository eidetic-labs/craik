"""Agent shell, readiness, model, session, profile, and usage CLI commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from craik.cli import app, model_app, profile_app, session_app
from craik.cli_prompt_safety import resolve_cli_prompt
from craik.runtime.auth.visibility import active_operator_session_from_env
from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.model_commands import (
    model_alias_result,
    model_fallback_result,
    model_list_result,
    model_probe_result,
    model_set_result,
    model_status_result,
)
from craik.runtime.shell.agent_shell import one_shot_response, run_shell
from craik.runtime.shell.profile_settings import (
    CraikUserProfile,
    ProfileSettings,
    ProfileSettingsStore,
)
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore


@app.command("chat")
def chat_command(
    prompt: Annotated[
        str | None,
        typer.Option("-q", "--prompt", help="Run one prompt; pass '-' to read stdin."),
    ] = None,
    allow_argv_prompt: Annotated[
        bool,
        typer.Option(
            "--allow-argv-prompt",
            help="Acknowledge argv prompt exposure in process listings and shell history.",
        ),
    ] = False,
) -> None:
    """Launch the Craik agent shell or run one conversational prompt."""
    if prompt is not None:
        typer.echo(one_shot_response(resolve_cli_prompt(prompt, allow_argv=allow_argv_prompt)))
        raise typer.Exit()
    raise typer.Exit(run_shell())


@app.command("slash")
def slash_command(command: str) -> None:
    """Dispatch one slash command for tests and shell integrations."""
    result = dispatch_slash_command(command)
    typer.echo(result.text)
    raise typer.Exit(result.exit_code)


@model_app.command("list")
@craik_command(slash_alias="model-list", payload_shape="kv")
def model_list() -> CommandResult:
    """List configured provider/model choices and local presets."""
    result = model_list_result()
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@model_app.command("status")
@craik_command(slash_alias="model", payload_shape="kv")
def model_status() -> CommandResult:
    """Show active model state and readiness."""
    result = model_status_result()
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@model_app.command("set")
@craik_command(payload_shape="kv")
def model_set(model: str) -> CommandResult:
    """Set the active model as <provider>/<model>."""
    try:
        result = model_set_result(model)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@model_app.command("probe")
@craik_command(payload_shape="kv")
def model_probe() -> CommandResult:
    """Probe model readiness without sending live prompts."""
    result = model_probe_result()
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@model_app.command("alias")
@craik_command(payload_shape="kv")
def model_alias(
    action: str,
    name: str | None = None,
    target: str | None = None,
) -> CommandResult:
    """List, add, or remove model aliases."""
    try:
        result = model_alias_result(action, name, target)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@model_app.command("fallback")
@craik_command(payload_shape="kv")
def model_fallback(action: str, model: str | None = None) -> CommandResult:
    """List, add, remove, or clear model fallback order."""
    try:
        result = model_fallback_result(action, model)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(result.payload, indent=2, sort_keys=True))
    return result


@session_app.command("list")
def session_list() -> None:
    """List persistent agent sessions."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        sessions = [_session_payload(session) for session in store.list_agent_session_states()]
    finally:
        store.close()
    typer.echo(json.dumps(sessions, indent=2, sort_keys=True))


@session_app.command("show")
def session_show(session_id: str) -> None:
    """Show one persistent agent session."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
    finally:
        store.close()
    if session is None:
        raise typer.BadParameter(f"unknown session: {session_id}")
    typer.echo(json.dumps(_session_payload(session), indent=2, sort_keys=True))


@session_app.command("resume")
def session_resume(session_id: str) -> None:
    """Print resume guidance for one persistent session."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
    finally:
        store.close()
    if session is None:
        raise typer.BadParameter(f"unknown session: {session_id}")
    payload = {
        "session_id": session.id,
        "status": session.status,
        "resume_supported": session.status in {"idle", "stopped", "auth_expired"},
        "next_action": f"craik session show {session.id}",
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@session_app.command("rename")
def session_rename(session_id: str, name: str) -> None:
    """Assign a display name to a persistent session."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
        if session is None:
            raise typer.BadParameter(f"unknown session: {session_id}")
        metadata = dict(session.recovery_metadata)
        metadata["name"] = name
        updated = session.model_copy(update={"recovery_metadata": metadata, "updated_at": _now()})
        store.put_agent_session_state(updated)
    finally:
        store.close()
    typer.echo(json.dumps(_session_payload(updated), indent=2, sort_keys=True))


@session_app.command("export")
def session_export(session_id: str) -> None:
    """Export one redacted persistent session."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
    finally:
        store.close()
    if session is None:
        raise typer.BadParameter(f"unknown session: {session_id}")
    payload = _session_payload(session)
    payload["redacted"] = True
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@session_app.command("prune")
def session_prune(
    yes: Annotated[bool, typer.Option("--yes", help="Confirm pruning stopped sessions.")] = False,
) -> None:
    """Preview pruning stopped sessions; destructive deletion is not performed."""
    _operator_identity()
    if not yes:
        raise typer.BadParameter("session prune requires --yes")
    store = LocalStore.from_env()
    try:
        store.initialize()
        stopped = [
            session.id
            for session in store.list_agent_session_states()
            if session.status in {"stopped", "failed"}
        ]
    finally:
        store.close()
    typer.echo(json.dumps({"prunable": stopped, "deleted": []}, indent=2, sort_keys=True))


@session_app.command("delete")
def session_delete(
    session_id: str,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm session deletion.")] = False,
) -> None:
    """Mark a session as stopped; raw record deletion is intentionally not supported."""
    _operator_identity()
    if not yes:
        raise typer.BadParameter("session delete requires --yes")
    store = LocalStore.from_env()
    try:
        store.initialize()
        session = store.get_agent_session_state(session_id)
        if session is None:
            raise typer.BadParameter(f"unknown session: {session_id}")
        updated = session.model_copy(
            update={
                "status": "stopped",
                "stopped_at": _now(),
                "updated_at": _now(),
                "supervision_notes": [*session.supervision_notes, "marked stopped by CLI delete"],
            }
        )
        store.put_agent_session_state(updated)
    finally:
        store.close()
    typer.echo(json.dumps({"session_id": session_id, "marked_stopped": True}, indent=2))


@profile_app.command("list")
def profile_list() -> None:
    """List local Craik profiles."""
    settings = ProfileSettingsStore.from_env().load()
    typer.echo(json.dumps(settings.as_dict(), indent=2, sort_keys=True))


@profile_app.command("use")
def profile_use(name: str) -> None:
    """Set the active local Craik profile."""
    store = ProfileSettingsStore.from_env()
    settings = store.load()
    if name not in settings.profiles:
        raise typer.BadParameter(f"unknown profile: {name}")
    updated = ProfileSettings(active=name, profiles=settings.profiles)
    store.save(updated)
    typer.echo(json.dumps(updated.as_dict(), indent=2, sort_keys=True))


@profile_app.command("create")
def profile_create(
    name: str,
    description: Annotated[str, typer.Option("--description")] = "",
) -> None:
    """Create a local Craik profile."""
    store = ProfileSettingsStore.from_env()
    settings = store.load()
    profiles = dict(settings.profiles)
    profiles[name] = CraikUserProfile(name=name, description=description)
    updated = ProfileSettings(active=settings.active, profiles=profiles)
    store.save(updated)
    typer.echo(json.dumps(updated.as_dict(), indent=2, sort_keys=True))


@profile_app.command("show")
def profile_show(name: str | None = None) -> None:
    """Show one local Craik profile."""
    settings = ProfileSettingsStore.from_env().load()
    selected = name or settings.active
    try:
        profile = settings.profiles[selected]
    except KeyError:
        raise typer.BadParameter(f"unknown profile: {selected}") from None
    typer.echo(json.dumps(profile.as_dict(), indent=2, sort_keys=True))


@profile_app.command("rename")
def profile_rename(old: str, new: str) -> None:
    """Rename a local Craik profile."""
    store = ProfileSettingsStore.from_env()
    settings = store.load()
    if old not in settings.profiles:
        raise typer.BadParameter(f"unknown profile: {old}")
    profiles = dict(settings.profiles)
    profile = profiles.pop(old)
    profiles[new] = CraikUserProfile(new, profile.description, profile.metadata)
    active = new if settings.active == old else settings.active
    updated = ProfileSettings(active=active, profiles=profiles)
    store.save(updated)
    typer.echo(json.dumps(updated.as_dict(), indent=2, sort_keys=True))


@profile_app.command("delete")
def profile_delete(
    name: str,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm profile deletion.")] = False,
) -> None:
    """Delete a local Craik profile."""
    if name == "default":
        raise typer.BadParameter("default profile cannot be deleted")
    if not yes:
        raise typer.BadParameter("profile delete requires --yes")
    store = ProfileSettingsStore.from_env()
    settings = store.load()
    profiles = dict(settings.profiles)
    profiles.pop(name, None)
    active = "default" if settings.active == name else settings.active
    updated = ProfileSettings(active=active, profiles=profiles)
    store.save(updated)
    typer.echo(json.dumps(updated.as_dict(), indent=2, sort_keys=True))


@profile_app.command("export")
def profile_export() -> None:
    """Export profile settings without secrets."""
    payload = ProfileSettingsStore.from_env().load().as_dict()
    payload["redacted"] = True
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@profile_app.command("import")
def profile_import(path: str) -> None:
    """Import profile settings from a redacted JSON export."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    profiles = {
        name: CraikUserProfile(
            name=name,
            description=str(value.get("description", "")),
            metadata={str(k): str(v) for k, v in dict(value.get("metadata", {})).items()},
        )
        for name, value in dict(payload.get("profiles", {})).items()
    }
    if "default" not in profiles:
        profiles["default"] = CraikUserProfile("default")
    settings = ProfileSettings(active=str(payload.get("active", "default")), profiles=profiles)
    ProfileSettingsStore.from_env().save(settings)
    typer.echo(json.dumps(settings.as_dict(), indent=2, sort_keys=True))


@app.command("insights")
def insights_command() -> None:
    """Show high-level runtime activity insights."""
    _operator_identity()
    typer.echo(json.dumps(_usage_payload(), indent=2, sort_keys=True))


@app.command("usage")
def usage_command() -> None:
    """Show provider, approval, and session usage summary."""
    _operator_identity()
    typer.echo(json.dumps(_usage_payload(), indent=2, sort_keys=True))


def _operator_identity() -> str:
    session = active_operator_session_from_env()
    if session is None:
        raise typer.BadParameter("active operator session required; run craik login")
    return session.subject


def _now() -> datetime:
    return datetime.now(UTC)


def _session_payload(session: Any) -> dict[str, object]:
    return {
        "id": session.id,
        "name": session.recovery_metadata.get("name") if session.recovery_metadata else None,
        "project_id": session.project_id,
        "operator_subject": session.operator_subject,
        "provider_id": session.provider_id,
        "model_id": session.model_id,
        "status": session.status,
        "mode": session.mode,
        "active_task_id": session.active_task_id,
        "active_run_id": session.active_run_id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "last_activity_at": session.last_activity_at.isoformat()
        if session.last_activity_at
        else None,
        "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
        "receipt_ids": session.receipt_ids,
        "handoff_ids": session.handoff_ids,
        "redacted": True,
    }


def _usage_payload() -> dict[str, object]:
    store = LocalStore.from_env()
    try:
        store.initialize()
        sessions = store.list_agent_session_states()
        receipts = store.list_receipts()
        handoffs = store.list_handoffs()
        delegations = store.list_human_delegations()
    finally:
        store.close()
    return {
        "provider_calls": "unknown",
        "token_usage": "unknown",
        "known_costs": "unknown",
        "failed_calls": "unknown",
        "approvals": len([item for item in delegations if item.status == "resolved"]),
        "denials": "unknown",
        "session_activity": {
            "sessions": len(sessions),
            "active": len([item for item in sessions if item.status in {"running", "idle"}]),
        },
        "skill_impact": "unknown",
        "receipts": len(receipts),
        "handoffs": len(handoffs),
    }
