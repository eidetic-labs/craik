"""Command-line interface for Craik."""

from __future__ import annotations

import json
import os
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer
from pydantic import ValidationError

from craik import __version__
from craik.cli_agents import agent_app
from craik.cli_approvals import approvals_app
from craik.cli_channels import channels_app
from craik.cli_diagnostics import doctor_command, update_command
from craik.cli_gateway import gateway_app
from craik.cli_prompt_safety import resolve_cli_prompt
from craik.cli_receipts import receipts_app
from craik.cli_runs import run_app
from craik.contracts.registry import schema_model, schema_names
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.companions.desktop_companion import (
    desktop_approval_notification,
    desktop_companion_action,
    desktop_companion_actions,
    desktop_companion_snapshot,
    desktop_update_check_payload,
)
from craik.runtime.dashboard import (
    DashboardConfig,
    DashboardConfigError,
    dashboard_preview_payload,
    run_dashboard_server,
)
from craik.runtime.gateway import (
    default_gateway_config,
    gateway_configured_state,
)
from craik.runtime.paths import (
    CraikPaths,
    ensure_craik_home,
    resolve_craik_home,
    resolve_craik_paths,
)
from craik.runtime.shell.agent_shell import one_shot_response, run_shell
from craik.runtime.shell.tui import run_tui
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
app.add_typer(channels_app, name="channels")
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
app.add_typer(approvals_app, name="approvals")
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
app.add_typer(gateway_app, name="gateway")
app.command("doctor")(doctor_command)
app.command("update")(update_command)
model_app = typer.Typer(help="Inspect and select active model routing.")
app.add_typer(model_app, name="model")
session_app = typer.Typer(help="Inspect and manage persistent Craik sessions.")
app.add_typer(session_app, name="session")
profile_app = typer.Typer(help="Manage local Craik profiles and personas.")
app.add_typer(profile_app, name="profile")
desktop_app = typer.Typer(help="Inspect and launch desktop companion MVP actions.")
app.add_typer(desktop_app, name="desktop")
migrate_app = typer.Typer(help="Inspect and dry-run adjacent runtime migrations.")
app.add_typer(migrate_app, name="migrate")


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
        typer.Option(
            "-z",
            "--one-shot",
            help=(
                "Run one quiet one-shot prompt and exit. Pass '-' to read "
                "the prompt from stdin."
            ),
        ),
    ] = None,
    allow_argv_prompt: Annotated[
        bool,
        typer.Option(
            "--allow-argv-prompt",
            help=(
                "Acknowledge that argv prompts are visible in local process "
                "listings and shell history."
            ),
        ),
    ] = False,
    tui_requested: Annotated[
        bool,
        typer.Option(
            "--tui",
            help="Launch the keyboard-first terminal UI.",
        ),
    ] = False,
) -> None:
    """Run Craik."""
    if version_requested:
        typer.echo(package_version())
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        if tui_requested:
            raise typer.Exit(run_tui())
        if one_shot is not None:
            prompt = resolve_cli_prompt(one_shot, allow_argv=allow_argv_prompt)
            typer.echo(one_shot_response(prompt))
            raise typer.Exit()
        raise typer.Exit(run_shell())


@app.command("version")
def version_command() -> None:
    """Print the installed Craik version."""
    typer.echo(package_version())


@app.command("tui")
def tui_command() -> None:
    """Launch the keyboard-first terminal UI."""
    raise typer.Exit(run_tui())


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


@app.command("dashboard")
def dashboard_command(
    host: Annotated[
        str,
        typer.Option("--host", help="Dashboard bind host. Defaults to local only."),
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8787,
    auth_token: Annotated[
        str | None,
        typer.Option("--auth-token", help="Dashboard bearer token; defaults to operator session."),
    ] = None,
    allow_unsafe_dashboard_bind: Annotated[
        bool,
        typer.Option(
            "--allow-unsafe-dashboard-bind",
            help="Allow binding the dashboard outside localhost.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print dashboard launch metadata without serving."),
    ] = False,
) -> None:
    """Run the authenticated local dashboard."""
    config = DashboardConfig(
        host=host,
        port=port,
        auth_token=auth_token or os.environ.get("CRAIK_DASHBOARD_TOKEN"),
        allow_unsafe_bind=allow_unsafe_dashboard_bind,
    )
    try:
        if dry_run:
            typer.echo(json.dumps(dashboard_preview_payload(config), indent=2, sort_keys=True))
            return
        typer.echo(json.dumps(dashboard_preview_payload(config), indent=2, sort_keys=True))
        run_dashboard_server(config)
    except DashboardConfigError as error:
        raise typer.BadParameter(str(error)) from None


@desktop_app.command("status")
def desktop_status_command() -> None:
    """Show desktop companion status, dashboard link, and gateway/provider health."""
    payload = desktop_companion_snapshot().model_dump(mode="json")
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@desktop_app.command("menu")
def desktop_menu_command() -> None:
    """List desktop companion tray/menu actions."""
    payload = [action.model_dump(mode="json") for action in desktop_companion_actions()]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@desktop_app.command("action")
def desktop_action_command(action_id: str) -> None:
    """Show the command backing one desktop companion action."""
    try:
        action = desktop_companion_action(action_id)
    except KeyError:
        raise typer.BadParameter(f"unknown desktop companion action: {action_id}") from None
    typer.echo(json.dumps(action.model_dump(mode="json"), indent=2, sort_keys=True))


@desktop_app.command("notify-approval")
def desktop_notify_approval_command(
    approval_id: str,
    capability: str,
    target: str,
    risk: Annotated[str, typer.Option("--risk", help="Approval risk summary.")] = (
        "operator review required"
    ),
    policy: Annotated[str, typer.Option("--policy", help="Policy profile or envelope.")] = "strict",
    retry_path: Annotated[str, typer.Option("--retry-path", help="Retry path after decision.")] = (
        "retry the blocked command after approval"
    ),
) -> None:
    """Render a desktop approval notification fixture."""
    payload = desktop_approval_notification(
        approval_id,
        capability=capability,
        target=target,
        risk=risk,
        policy=policy,
        retry_path=retry_path,
    ).model_dump(mode="json")
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@desktop_app.command("update-check")
def desktop_update_check_command() -> None:
    """Show the desktop companion update-check payload."""
    typer.echo(
        json.dumps(
            desktop_update_check_payload(package_version()),
            indent=2,
            sort_keys=True,
        )
    )


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
        "craik.cli_auth_login",
        "craik.cli_shell",
        "craik.cli_delegations",
        "craik.cli_handoffs",
        "craik.cli_instructions",
        "craik.cli_knowledge",
        "craik.cli_migration",
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
