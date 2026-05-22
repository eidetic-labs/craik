"""Command-line interface for Craik."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from craik import __version__
from craik.cli_agents import agent_app
from craik.cli_receipts import receipts_app
from craik.cli_runs import run_app
from craik.contracts.registry import schema_model, schema_names
from craik.runtime.auth import AuthProfileStore
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.doctor import run_doctor
from craik.runtime.gateway import (
    GatewayDaemonError,
    default_gateway_config,
    gateway_configured_state,
    run_gateway_daemon,
)
from craik.runtime.paths import (
    CraikPaths,
    ensure_craik_home,
    resolve_craik_home,
    resolve_craik_paths,
)
from craik.runtime.projects.update_guidance import update_guidance_payload
from craik.runtime.shell.agent_shell import one_shot_response, run_shell
from craik.runtime.shell.model_settings import ModelSettings, ModelSettingsStore
from craik.runtime.shell.profile_settings import (
    CraikUserProfile,
    ProfileSettings,
    ProfileSettingsStore,
)
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import DATABASE_NAME, LocalStore

PACKAGE_NAME = "craik"

app = typer.Typer(
    add_completion=False,
    help="Governed agent-runtime substrate for case files, policy, receipts, and providers.",
    no_args_is_help=False,
)
schema_app = typer.Typer(help="Inspect Craik runtime contract schemas.")
app.add_typer(schema_app, name="schema")
home_app = typer.Typer(help="Inspect and initialize Craik local state paths.")
app.add_typer(home_app, name="home")
project_app = typer.Typer(help="Register and inspect Craik projects.")
app.add_typer(project_app, name="project")
task_app = typer.Typer(help="Create and inspect Craik tasks.")
app.add_typer(task_app, name="task")
intent_app = typer.Typer(help="Inspect task intent locks.")
app.add_typer(intent_app, name="intent")
case_app = typer.Typer(help="Build and inspect Craik case files.")
app.add_typer(case_app, name="case")
connect_app = typer.Typer(help="Connect to external services.")
app.add_typer(connect_app, name="connect")
demo_app = typer.Typer(help="Run built-in Craik demos.")
app.add_typer(demo_app, name="demo")
delegation_app = typer.Typer(help="Pause and resolve human delegation points.")
app.add_typer(delegation_app, name="delegation")
scope_change_app = typer.Typer(help="Decide pending scope-change protocol requests.")
app.add_typer(scope_change_app, name="scope-change")
agent_message_app = typer.Typer(help="Send and receive agent mailbox messages.")
app.add_typer(agent_message_app, name="agent-message")
app.add_typer(agent_app, name="agent")
auth_app = typer.Typer(help="Manage provider credential profiles.")
app.add_typer(auth_app, name="auth")
contradictions_app = typer.Typer(help="Manage local contradiction reports.")
app.add_typer(contradictions_app, name="contradictions")
graph_app = typer.Typer(help="Export Craik work graphs.")
app.add_typer(graph_app, name="graph")
handoff_app = typer.Typer(help="Create and inspect Craik handoffs.")
app.add_typer(handoff_app, name="handoff")
memory_app = typer.Typer(help="Create and review local memory proposals.")
app.add_typer(memory_app, name="memory")
policy_app = typer.Typer(help="Inspect Craik policy profiles.")
app.add_typer(policy_app, name="policy")
app.add_typer(receipts_app, name="receipts")
app.add_typer(run_app, name="run")
runners_app = typer.Typer(help="Inspect runner capabilities and trust profiles.")
app.add_typer(runners_app, name="runners")
prompt_app = typer.Typer(help="Compile runner-ready prompts from Craik runtime state.")
app.add_typer(prompt_app, name="prompt")
provider_app = typer.Typer(help="Inspect and select model providers.")
app.add_typer(provider_app, name="provider")
instructions_app = typer.Typer(help="Manage runtime instruction distillation.")
app.add_typer(instructions_app, name="instructions")
knowledge_app = typer.Typer(help="Capture v0.5 runtime knowledge records.")
app.add_typer(knowledge_app, name="knowledge")
review_app = typer.Typer(help="Capture reviewable critic and red-team findings.")
app.add_typer(review_app, name="review")
skills_app = typer.Typer(help="Install and inspect governed skill packages.")
app.add_typer(skills_app, name="skills")
plugins_app = typer.Typer(help="Install and govern runtime plugins.")
app.add_typer(plugins_app, name="plugins")
references_app = typer.Typer(help="Inspect and verify reference integrations.")
app.add_typer(references_app, name="references")
operator_app = typer.Typer(help="Inspect read-only operator surface state.")
app.add_typer(operator_app, name="operator")
gateway_app = typer.Typer(help="Run and inspect the local gateway daemon.")
app.add_typer(gateway_app, name="gateway")
model_app = typer.Typer(help="Inspect and select active model routing.")
app.add_typer(model_app, name="model")
session_app = typer.Typer(help="Inspect and manage persistent Craik sessions.")
app.add_typer(session_app, name="session")
profile_app = typer.Typer(help="Manage local Craik profiles and personas.")
app.add_typer(profile_app, name="profile")


def package_version() -> str:
    """Return the installed package version, with a source-tree fallback."""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return __version__


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version_requested: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print the installed Craik version and exit.",
        ),
    ] = False,
    one_shot: Annotated[
        str | None,
        typer.Option("-z", "--one-shot", help="Run one quiet one-shot prompt and exit."),
    ] = None,
) -> None:
    """Run Craik."""
    if version_requested:
        typer.echo(package_version())
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        if one_shot is not None:
            typer.echo(one_shot_response(one_shot))
            raise typer.Exit()
        raise typer.Exit(run_shell())


@app.command("chat")
def chat_command(
    prompt: Annotated[
        str | None,
        typer.Option("-q", "--prompt", help="Run one conversational prompt and exit."),
    ] = None,
) -> None:
    """Launch the Craik agent shell or run one conversational prompt."""
    if prompt is not None:
        typer.echo(one_shot_response(prompt))
        raise typer.Exit()
    raise typer.Exit(run_shell())


@app.command("status")
def status_command() -> None:
    """Show progressive setup readiness for shell and runtime actions."""
    typer.echo(json.dumps(resolve_readiness().as_dict(), indent=2, sort_keys=True))


@app.command("slash")
def slash_command(command: str) -> None:
    """Dispatch one slash command for tests and shell integrations."""
    result = dispatch_slash_command(command)
    typer.echo(result.text)
    raise typer.Exit(result.exit_code)


@app.command("version")
def version_command() -> None:
    """Print the installed Craik version."""
    typer.echo(package_version())


@app.command("setup")
def setup_command(
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Optional project id for gateway configuration."),
    ] = None,
    gateway_enabled: Annotated[
        bool,
        typer.Option(
            "--enable-gateway/--disable-gateway",
            help="Enable or disable the persisted gateway configuration.",
        ),
    ] = False,
    gateway_bind_host: Annotated[
        str,
        typer.Option("--gateway-bind-host", help="Gateway bind host. Defaults to local only."),
    ] = "127.0.0.1",
    gateway_port: Annotated[
        int,
        typer.Option("--gateway-port", help="Gateway port."),
    ] = 8765,
    policy_envelope_id: Annotated[
        str | None,
        typer.Option("--policy-envelope-id", help="Policy envelope for gateway authority."),
    ] = None,
    allow_insecure_public_gateway: Annotated[
        bool,
        typer.Option(
            "--allow-insecure-public-gateway",
            help="Explicitly allow a public gateway bind without TLS termination.",
        ),
    ] = False,
) -> None:
    """Initialize local state and write non-secret gateway setup output."""
    resolved_paths = resolve_craik_paths()
    if (resolved_paths.state / DATABASE_NAME).exists():
        _operator_identity()
    public_bind = gateway_bind_host in {"0.0.0.0", "::"}  # nosec B104
    if public_bind and policy_envelope_id and not allow_insecure_public_gateway:
        raise typer.BadParameter(
            "public gateway bind without TLS requires --allow-insecure-public-gateway"
        )
    paths = ensure_craik_home()
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = default_gateway_config(
            project_id=project_id,
            policy_envelope_id=policy_envelope_id,
        ).model_copy(
            update={
                "bind_host": gateway_bind_host,
                "port": gateway_port,
                "enabled": gateway_enabled,
            }
        )
        try:
            config = type(config).model_validate(config.model_dump(mode="json", by_alias=True))
        except ValidationError as error:
            raise typer.BadParameter(str(error)) from None
        store.put_gateway_config(config)
        runtime_state = gateway_configured_state(config)
        store.put_gateway_runtime_state(runtime_state)
        payload = {
            "home": _paths_payload(paths),
            "gateway_config": config.model_dump(mode="json", by_alias=True),
            "gateway_runtime_state": runtime_state.model_dump(mode="json", by_alias=True),
            "secrets_written": False,
            "next_steps": [
                "Review gateway_config before enabling external ingress.",
                "Store channel secrets outside Craik config files.",
                "Run gateway diagnostics before starting the daemon.",
            ],
        }
        if public_bind:
            payload["warnings"] = [
                "Public gateway bind configured without TLS termination; place it behind TLS "
                "or keep it on a private network."
            ]
    finally:
        store.close()

    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("doctor")
def doctor_command() -> None:
    """Run read-only diagnostics for local and gateway readiness."""
    _operator_identity()
    paths = resolve_craik_paths()
    payload = run_doctor(paths, env=dict(os.environ))
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("update")
def update_command() -> None:
    """Print safe update guidance without modifying the installation."""
    payload = update_guidance_payload(installed_version=package_version())
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@model_app.command("list")
def model_list() -> None:
    """List configured provider/model choices and local presets."""
    settings = ModelSettingsStore.from_env().load()
    try:
        auth_profiles = [
            {
                "id": profile.id,
                "provider_family": profile.provider_family,
                "last_status": profile.last_status,
            }
            for profile in AuthProfileStore.from_env().list()
        ]
    except Exception:
        auth_profiles = []
    payload = {
        "active_model": settings.active_model,
        "aliases": settings.aliases,
        "fallbacks": settings.fallbacks,
        "configured_profiles": auth_profiles,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@model_app.command("status")
def model_status() -> None:
    """Show active model state and readiness."""
    settings = ModelSettingsStore.from_env().load()
    readiness = resolve_readiness()
    payload = {
        "active_model": settings.active_model,
        "readiness": readiness.as_dict(),
        "aliases": settings.aliases,
        "fallbacks": settings.fallbacks,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@model_app.command("set")
def model_set(model: str) -> None:
    """Set the active model as <provider>/<model>."""
    _validate_model_ref(model)
    store = ModelSettingsStore.from_env()
    settings = store.load()
    updated = ModelSettings(
        active_model=model,
        aliases=settings.aliases,
        fallbacks=settings.fallbacks,
    )
    store.save(updated)
    typer.echo(json.dumps(updated.as_dict(), indent=2, sort_keys=True))


@model_app.command("probe")
def model_probe() -> None:
    """Probe model readiness without sending live prompts."""
    settings = ModelSettingsStore.from_env().load()
    readiness = resolve_readiness()
    payload = {
        "active_model": settings.active_model,
        "can_execute": readiness.state == "fully-ready" and settings.active_model is not None,
        "state": readiness.state,
        "missing": readiness.missing,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@model_app.command("alias")
def model_alias(action: str, name: str | None = None, target: str | None = None) -> None:
    """List, add, or remove model aliases."""
    store = ModelSettingsStore.from_env()
    settings = store.load()
    aliases = dict(settings.aliases)
    if action == "list":
        typer.echo(json.dumps(aliases, indent=2, sort_keys=True))
        return
    if action == "add" and name and target:
        _validate_model_ref(target)
        aliases[name] = target
    elif action == "remove" and name:
        aliases.pop(name, None)
    else:
        raise typer.BadParameter(
            "expected alias list, alias add <name> <target>, or alias remove <name>"
        )
    updated = ModelSettings(settings.active_model, aliases, settings.fallbacks)
    store.save(updated)
    typer.echo(json.dumps(updated.as_dict(), indent=2, sort_keys=True))


@model_app.command("fallback")
def model_fallback(action: str, model: str | None = None) -> None:
    """List, add, remove, or clear model fallback order."""
    store = ModelSettingsStore.from_env()
    settings = store.load()
    fallbacks = list(settings.fallbacks)
    if action == "list":
        typer.echo(json.dumps(fallbacks, indent=2, sort_keys=True))
        return
    if action == "add" and model:
        _validate_model_ref(model)
        fallbacks = [item for item in fallbacks if item != model]
        fallbacks.append(model)
    elif action == "remove" and model:
        fallbacks = [item for item in fallbacks if item != model]
    elif action == "clear":
        fallbacks = []
    else:
        raise typer.BadParameter("expected fallback list, add <model>, remove <model>, or clear")
    updated = ModelSettings(settings.active_model, settings.aliases, fallbacks)
    store.save(updated)
    typer.echo(json.dumps(updated.as_dict(), indent=2, sort_keys=True))


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


@gateway_app.command("start")
def gateway_start_command() -> None:
    """Run the foreground gateway daemon until interrupted."""
    _operator_identity()
    paths = resolve_craik_paths()
    try:
        state = run_gateway_daemon(paths)
    except GatewayDaemonError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(state.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@schema_app.command("list")
def schema_list() -> None:
    """List known Craik contract schemas."""
    for name in schema_names():
        typer.echo(name)


@schema_app.command("show")
def schema_show(name: str) -> None:
    """Print a contract JSON Schema by name."""
    try:
        model = schema_model(name)
    except KeyError:
        known = ", ".join(schema_names())
        raise typer.BadParameter(f"unknown schema {name!r}; known schemas: {known}") from None

    typer.echo(json.dumps(model.model_json_schema(), indent=2, sort_keys=True))




def _paths_payload(paths: CraikPaths) -> dict[str, str]:
    return {
        "cache": str(paths.cache),
        "case_files": str(paths.case_files),
        "config": str(paths.config),
        "handoffs": str(paths.handoffs),
        "home": str(paths.home),
        "logs": str(paths.logs),
        "projects": str(paths.projects),
        "receipts": str(paths.receipts),
        "secrets": str(paths.secrets),
        "state": str(paths.state),
    }


def _validate_model_ref(value: str) -> None:
    if "/" not in value or value.startswith("/") or value.endswith("/"):
        raise typer.BadParameter("model reference must be formatted as <provider>/<model>")


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


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore(resolve_craik_home()).get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik auth login") from None
    return session.subject


def _load_cli_extensions() -> None:
    """Import command modules that register subcommands on shared Typer apps."""
    for module_name in (
        "craik.cli_agent_messages",
        "craik.cli_auth",
        "craik.cli_delegations",
        "craik.cli_handoffs",
        "craik.cli_instructions",
        "craik.cli_knowledge",
        "craik.cli_operations",
        "craik.cli_project",
        "craik.cli_provider_certification",
        "craik.cli_provider_local",
        "craik.cli_review",
        "craik.cli_scope_changes",
        "craik.cli_skills",
        "craik.cli_plugins",
        "craik.cli_references",
        "craik.cli_operator",
        "craik.cli_operator_continuity",
        "craik.cli_tasks",
    ):
        import_module(module_name)


_load_cli_extensions()


def main() -> None:
    app()
