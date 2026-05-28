"""Command-line interface for Craik."""
from __future__ import annotations

import os
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer

from craik import __version__
from craik.cli_agents import agent_app
from craik.cli_approvals import approvals_app
from craik.cli_channels import channels_app
from craik.cli_diagnostics import doctor_command, update_command
from craik.cli_errors import install_craik_error_handler
from craik.cli_gateway import gateway_app
from craik.cli_output import emit_command_result
from craik.cli_prompt_safety import resolve_cli_prompt
from craik.cli_receipts import receipts_app
from craik.cli_runs import run_app
from craik.cli_session import env_with_session_name
from craik.cli_typer import craik_typer
from craik.contracts.registry import schema_model, schema_names
from craik.runtime.backend.jsonl import run_jsonl_gateway
from craik.runtime.companions.desktop_companion import (
    desktop_approval_notification,
    desktop_companion_action,
    desktop_companion_actions,
    desktop_companion_snapshot,
    desktop_update_check_payload,
)
from craik.runtime.contract import CommandResult, PayloadShape, craik_command
from craik.runtime.dashboard import (
    DashboardConfig,
    DashboardConfigError,
    dashboard_preview_payload,
    run_dashboard_server,
)
from craik.runtime.setup import (
    SetupOperatorSessionRequiredError,
    setup_command_result,
)
from craik.runtime.shell.agent_shell import one_shot_response, run_shell
from craik.runtime.shell.tui import run_tui

PACKAGE_NAME = "craik"
install_craik_error_handler()
app = craik_typer(
    add_completion=False,
    help="Governed agent-runtime substrate for case files, policy, receipts, and providers.",
    no_args_is_help=False,
)
schema_app = craik_typer(help="Inspect Craik runtime contract schemas.")
app.add_typer(schema_app, name="schema")
home_app = craik_typer(help="Inspect and initialize Craik local state paths.")
app.add_typer(home_app, name="home")
project_app = craik_typer(help="Register and inspect Craik projects.")
app.add_typer(project_app, name="project")
task_app = craik_typer(help="Create and inspect Craik tasks.")
app.add_typer(task_app, name="task")
intent_app = craik_typer(help="Inspect task intent locks.")
app.add_typer(intent_app, name="intent")
case_app = craik_typer(help="Build and inspect Craik case files.")
app.add_typer(case_app, name="case")
connect_app = craik_typer(help="Connect to external services.")
app.add_typer(connect_app, name="connect")
app.add_typer(channels_app, name="channels")
demo_app = craik_typer(help="Run built-in Craik demos.")
app.add_typer(demo_app, name="demo")
delegation_app = craik_typer(help="Pause and resolve human delegation points.")
app.add_typer(delegation_app, name="delegation")
scope_change_app = craik_typer(help="Decide pending scope-change protocol requests.")
app.add_typer(scope_change_app, name="scope-change")
agent_message_app = craik_typer(help="Send and receive agent mailbox messages.")
app.add_typer(agent_message_app, name="agent-message")
app.add_typer(agent_app, name="agent")
auth_app = craik_typer(help="Manage provider credential profiles.")
app.add_typer(auth_app, name="auth")
app.add_typer(approvals_app, name="approvals")
contradictions_app = craik_typer(help="Manage local contradiction reports.")
app.add_typer(contradictions_app, name="contradictions")
graph_app = craik_typer(help="Export Craik work graphs.")
app.add_typer(graph_app, name="graph")
handoff_app = craik_typer(help="Create and inspect Craik handoffs.")
app.add_typer(handoff_app, name="handoff")
memory_app = craik_typer(help="Create and review local memory proposals.")
app.add_typer(memory_app, name="memory")
policy_app = craik_typer(help="Inspect Craik policy profiles.")
app.add_typer(policy_app, name="policy")
app.add_typer(receipts_app, name="receipts")
app.add_typer(receipts_app, name="receipt")
app.add_typer(run_app, name="run")
runners_app = craik_typer(help="Inspect runner capabilities and trust profiles.")
app.add_typer(runners_app, name="runners")
prompt_app = craik_typer(help="Compile runner-ready prompts from Craik runtime state.")
app.add_typer(prompt_app, name="prompt")
provider_app = craik_typer(help="Inspect and select model providers.")
app.add_typer(provider_app, name="provider")
instructions_app = craik_typer(help="Manage runtime instruction distillation.")
app.add_typer(instructions_app, name="instructions")
knowledge_app = craik_typer(help="Capture v0.5 runtime knowledge records.")
app.add_typer(knowledge_app, name="knowledge")
review_app = craik_typer(help="Capture reviewable critic and red-team findings.")
app.add_typer(review_app, name="review")
skills_app = craik_typer(help="Install and inspect governed skill packages.")
app.add_typer(skills_app, name="skills")
plugins_app = craik_typer(help="Install and govern runtime plugins.")
app.add_typer(plugins_app, name="plugins")
references_app = craik_typer(help="Inspect and verify reference integrations.")
app.add_typer(references_app, name="references")
operator_app = craik_typer(help="Inspect read-only operator surface state.")
app.add_typer(operator_app, name="operator")
app.add_typer(gateway_app, name="gateway")
app.command("doctor")(doctor_command)
app.command("update")(update_command)
model_app = craik_typer(help="Inspect and select active model routing.")
app.add_typer(model_app, name="model")
session_app = craik_typer(help="Inspect and manage persistent Craik sessions.")
app.add_typer(session_app, name="session")
profile_app = craik_typer(help="Manage local Craik profiles and personas.")
app.add_typer(profile_app, name="profile")
desktop_app = craik_typer(help="Inspect and launch desktop companion MVP actions.")
app.add_typer(desktop_app, name="desktop")
migrate_app = craik_typer(help="Inspect and dry-run adjacent runtime migrations.")
app.add_typer(migrate_app, name="migrate")
mcp_app = craik_typer(help="Inspect MCP server and client compatibility.")
app.add_typer(mcp_app, name="mcp")

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
    no_tui: Annotated[
        bool,
        typer.Option(
            "--no-tui",
            help="Force the plain shell even when running in an interactive terminal.",
        ),
    ] = False,
    session_name: Annotated[
        str | None,
        typer.Option("-n", "--name", help="Operator-visible shell session name."),
    ] = None,
) -> None:
    """Run Craik."""
    if version_requested:
        typer.echo(package_version())
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        env = env_with_session_name(session_name)
        if tui_requested:
            raise typer.Exit(run_tui(env=env))
        if one_shot is not None:
            prompt = resolve_cli_prompt(one_shot, allow_argv=allow_argv_prompt)
            typer.echo(one_shot_response(prompt, env=env))
            raise typer.Exit()
        if (
            not no_tui
            and env.get("CRAIK_NO_TUI") != "1"
            and env.get("TERM") != "dumb"
            and os.isatty(0)
            and os.isatty(1)
        ):
            raise typer.Exit(run_tui(env=env))
        raise typer.Exit(run_shell(env=env))


@app.command("version")
def version_command() -> None:
    """Print the installed Craik version."""
    typer.echo(package_version())


@app.command("tui")
def tui_command(
    session_name: Annotated[
        str | None,
        typer.Option("-n", "--name", help="Operator-visible shell session name."),
    ] = None,
) -> None:
    """Launch the keyboard-first terminal UI."""
    raise typer.Exit(run_tui(env=env_with_session_name(session_name)))


@app.command("tui-backend")
def tui_backend_command(
    jsonl: Annotated[
        bool,
        typer.Option("--jsonl", help="Run the local Gateway session over JSONL stdio."),
    ] = False,
    session_name: Annotated[
        str | None,
        typer.Option("-n", "--name", help="Operator-visible backend session name."),
    ] = None,
) -> None:
    """Run the backend protocol used by TUI clients."""
    if not jsonl:
        raise typer.BadParameter("tui-backend currently requires --jsonl")
    raise typer.Exit(run_jsonl_gateway(env=env_with_session_name(session_name)))


@app.command("setup")
@craik_command(payload_shape="kv")
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
) -> CommandResult:
    """Initialize local state and write non-secret gateway setup output."""
    try:
        result = setup_command_result(
            project_id=project_id,
            gateway_enabled=gateway_enabled,
            gateway_bind_host=gateway_bind_host,
            gateway_port=gateway_port,
            policy_envelope_id=policy_envelope_id,
            allow_insecure_public_gateway=allow_insecure_public_gateway,
        )
    except SetupOperatorSessionRequiredError:
        raise typer.BadParameter("active operator session required; run craik login") from None
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    emit_command_result(result)
    return result


@app.command("dashboard")
@craik_command(payload_shape="card")
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
) -> CommandResult:
    """Run the authenticated local dashboard."""
    config = DashboardConfig(
        host=host,
        port=port,
        auth_token=auth_token or os.environ.get("CRAIK_DASHBOARD_TOKEN"),
        allow_unsafe_bind=allow_unsafe_dashboard_bind,
    )
    try:
        payload = dashboard_preview_payload(config)
        result = _emit_payload(payload, shape="card")
        if dry_run:
            return result
        run_dashboard_server(config)
        return result
    except DashboardConfigError as error:
        raise typer.BadParameter(str(error)) from None


@desktop_app.command("status")
@craik_command(payload_shape="card")
def desktop_status_command() -> CommandResult:
    """Show desktop companion status, dashboard link, and gateway/provider health."""
    payload = desktop_companion_snapshot().model_dump(mode="json")
    return _emit_payload(payload, shape="card")


@desktop_app.command("menu")
@craik_command(payload_shape="card_list")
def desktop_menu_command() -> CommandResult:
    """List desktop companion tray/menu actions."""
    payload = [action.model_dump(mode="json") for action in desktop_companion_actions()]
    return _emit_payload(payload, shape="card_list")


@desktop_app.command("action")
@craik_command(payload_shape="card")
def desktop_action_command(action_id: str) -> CommandResult:
    """Show the command backing one desktop companion action."""
    try:
        action = desktop_companion_action(action_id)
    except KeyError:
        raise typer.BadParameter(f"unknown desktop companion action: {action_id}") from None
    return _emit_payload(action.model_dump(mode="json"), shape="card")


@desktop_app.command("notify-approval")
@craik_command(payload_shape="card")
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
) -> CommandResult:
    """Render a desktop approval notification fixture."""
    payload = desktop_approval_notification(
        approval_id,
        capability=capability,
        target=target,
        risk=risk,
        policy=policy,
        retry_path=retry_path,
    ).model_dump(mode="json")
    return _emit_payload(payload, shape="card")


@desktop_app.command("update-check")
@craik_command(payload_shape="card")
def desktop_update_check_command() -> CommandResult:
    """Show the desktop companion update-check payload."""
    return _emit_payload(desktop_update_check_payload(package_version()), shape="card")


@schema_app.command("list")
@craik_command(payload_shape="card_list")
def schema_list() -> CommandResult:
    """List known Craik contract schemas."""
    return _emit_payload(list(schema_names()), shape="card_list")


@schema_app.command("show")
@craik_command(payload_shape="card")
def schema_show(name: str) -> CommandResult:
    """Print a contract JSON Schema by name."""
    try:
        model = schema_model(name)
    except KeyError:
        known = ", ".join(schema_names())
        raise typer.BadParameter(f"unknown schema {name!r}; known schemas: {known}") from None

    return _emit_payload(model.model_json_schema(), shape="card")


def _emit_payload(payload: object, *, shape: PayloadShape) -> CommandResult:
    result = CommandResult(payload=payload, shape=shape)
    emit_command_result(result)
    return result


def _load_cli_extensions() -> None:
    """Import command modules that register subcommands on shared Typer apps."""
    for module_name in (
        "craik.cli_agent_messages",
        "craik.cli_auth",
        "craik.cli_auth_login",
        "craik.cli_status",
        "craik.cli_shell",
        "craik.cli_delegations",
        "craik.cli_handoffs",
        "craik.cli_instructions",
        "craik.cli_knowledge",
        "craik.cli_migration",
        "craik.cli_memory",
        "craik.cli_mcp",
        "craik.cli_new.cmd_attach",
        "craik.cli_new.cmd_compact_stub",
        "craik.cli_new.cmd_cost",
        "craik.cli_new.cmd_fork",
        "craik.cli_new.cmd_note",
        "craik.cli_new.cmd_quota",
        "craik.cli_new.cmd_redo",
        "craik.cli_new.cmd_share_stub",
        "craik.cli_new.cmd_who",
        "craik.cli_operations",
        "craik.cli_project",
        "craik.cli_provider_certification",
        "craik.cli_provider_local",
        "craik.cli_review",
        "craik.cli_scope_changes",
        "craik.cli_session_portability",
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
