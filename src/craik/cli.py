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
from craik.cli_receipts import receipts_app
from craik.cli_runs import run_app
from craik.contracts.registry import schema_model, schema_names
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
from craik.runtime.store import DATABASE_NAME, LocalStore

PACKAGE_NAME = "craik"

app = typer.Typer(
    add_completion=False,
    help="Governed agent-runtime substrate for case files, policy, receipts, and providers.",
    no_args_is_help=True,
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
) -> None:
    """Run Craik."""
    if version_requested:
        typer.echo(package_version())
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


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
