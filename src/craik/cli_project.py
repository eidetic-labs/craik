"""Core project, provider, prompt, case, connection, and demo CLI commands."""

from __future__ import annotations

import json
import os
from importlib import import_module
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from craik.cli import (
    case_app,
    home_app,
    intent_app,
    project_app,
    prompt_app,
    provider_app,
    runners_app,
    task_app,
)
from craik.contracts.models import Priority, TaskMode
from craik.runtime.github import GitHubClient, GitHubConfig, GitHubReadAdapter
from craik.runtime.paths import CraikPaths, ensure_craik_home, resolve_craik_paths
from craik.runtime.policy.intent_locks import IntentLockManager, IntentLockNotFoundError
from craik.runtime.projects.project_registry import NotGitRepositoryError, ProjectRegistry
from craik.runtime.projects.prompts import (
    PromptCaseFileNotFoundError,
    PromptCompiler,
    PromptTaskNotFoundError,
)
from craik.runtime.providers.model_providers import (
    ModelProviderNotFoundError,
    default_model_provider_registry,
    provider_selection_payload,
)
from craik.runtime.runners.runners import (
    default_runner_capability_matrices,
    get_runner_capability_matrix,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import (
    CaseFileAssembler,
    DiscoveryOverrides,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from craik.runtime.work.tasks import create_task

for _module_name in (
    "craik.cli_connect",
    "craik.cli_demos",
    "craik.cli_onboarding",
    "craik.cli_provider_local",
):
    import_module(_module_name)


@runners_app.command("matrix")
def runners_matrix(
    runner_id: Annotated[
        str | None,
        typer.Option("--runner", help="Runner id to inspect. Prints all runners when omitted."),
    ] = None,
) -> None:
    """Print runner capability matrix entries as JSON."""
    payload: Any
    if runner_id is None:
        payload = [
            matrix.model_dump(mode="json", by_alias=True)
            for matrix in default_runner_capability_matrices().values()
        ]
    else:
        try:
            payload = get_runner_capability_matrix(runner_id).model_dump(
                mode="json",
                by_alias=True,
            )
        except KeyError as error:
            raise typer.BadParameter(str(error)) from None

    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@provider_app.command("list")
def provider_list() -> None:
    """Print registered model providers as JSON."""
    registry = default_model_provider_registry()
    payload = [provider.model_dump(mode="json", by_alias=True) for provider in registry.list()]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@provider_app.command("show")
def provider_show(provider_id: str) -> None:
    """Print one model provider as JSON."""
    registry = default_model_provider_registry()
    try:
        provider = registry.require(provider_id)
    except ModelProviderNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    payload = provider.model_dump(mode="json", by_alias=True)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@provider_app.command("select")
def provider_select(
    provider_id: str,
    mode: Annotated[
        str,
        typer.Option("--mode", help="Provider mode to select."),
    ] = "chat",
    policy_envelope_id: Annotated[
        str | None,
        typer.Option("--policy-envelope-id", help="Policy envelope linked to this selection."),
    ] = None,
    receipt_id: Annotated[
        list[str] | None,
        typer.Option("--receipt-id", help="Receipt id linked to this selection."),
    ] = None,
) -> None:
    """Print a redacted provider selection payload."""
    registry = default_model_provider_registry()
    try:
        provider = registry.require(provider_id)
        payload = provider_selection_payload(
            provider,
            mode=mode,
            policy_envelope_id=policy_envelope_id,
            receipt_ids=receipt_id,
        )
    except (ModelProviderNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@prompt_app.command("compile")
def prompt_compile(
    task_id: str,
    runner_id: Annotated[
        str,
        typer.Option("--runner", help="Runner id from `craik runners matrix`."),
    ],
    expected_output_schema: Annotated[
        list[str] | None,
        typer.Option("--expected-output-schema", help="Expected output schema. May repeat."),
    ] = None,
) -> None:
    """Compile a deterministic policy-aware prompt for a task and runner."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        try:
            compiled = PromptCompiler(store).compile(
                task_id,
                runner_id=runner_id,
                expected_output_schemas=expected_output_schema,
            )
        except PromptTaskNotFoundError as error:
            raise typer.BadParameter(str(error)) from None
        except PromptCaseFileNotFoundError as error:
            raise typer.BadParameter(str(error)) from None
        except KeyError as error:
            raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(
        json.dumps(compiled.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


@home_app.command("show")
def home_show() -> None:
    """Print resolved Craik local state paths without creating directories."""
    paths = resolve_craik_paths()
    typer.echo(json.dumps(_paths_payload(paths), indent=2, sort_keys=True))


@home_app.command("init")
def home_init() -> None:
    """Create Craik local state directories."""
    paths = ensure_craik_home()
    typer.echo(json.dumps(_paths_payload(paths), indent=2, sort_keys=True))


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


@project_app.command("add")
def project_add(
    path: Annotated[
        Path,
        typer.Argument(help="Path inside the Git repository to register."),
    ],
    name: Annotated[
        str | None,
        typer.Option("--name", help="Project name. Defaults to the repository directory name."),
    ] = None,
    docs_path: Annotated[
        list[str] | None,
        typer.Option("--docs-path", help="Documentation path to include. May be repeated."),
    ] = None,
    immutable_path: Annotated[
        list[str] | None,
        typer.Option("--immutable-path", help="Immutable path to include. May be repeated."),
    ] = None,
    discovery_include: Annotated[
        list[str] | None,
        typer.Option(
            "--discovery-include",
            help="Context discovery include override. May be repeated.",
        ),
    ] = None,
    discovery_exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--discovery-exclude",
            help="Context discovery exclude override. May be repeated.",
        ),
    ] = None,
) -> None:
    """Register a Git project."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        registry = ProjectRegistry(store)
        project = registry.add_project(
            path,
            name=name,
            docs_paths=tuple(docs_path or ()),
            immutable_paths=tuple(immutable_path or ()),
            discovery_include=tuple(discovery_include or ()),
            discovery_exclude=tuple(discovery_exclude or ()),
        )
    except NotGitRepositoryError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(json.dumps(project.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@project_app.command("list")
def project_list() -> None:
    """List registered projects."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        registry = ProjectRegistry(store)
        projects = registry.list_projects()
    finally:
        store.close()

    payload = [project.model_dump(mode="json", by_alias=True) for project in projects]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@project_app.command("show")
def project_show(project: str) -> None:
    """Show one registered project by id or name."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        registry = ProjectRegistry(store)
        profile = registry.get_project(project)
    finally:
        store.close()

    if profile is None:
        raise typer.BadParameter(f"unknown project: {project}")
    typer.echo(json.dumps(profile.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))


@task_app.command("create")
def task_create(
    title: Annotated[str, typer.Option("--title", help="Task title.")],
    objective: Annotated[str, typer.Option("--objective", help="Task objective.")],
    project: Annotated[str, typer.Option("--project", help="Registered project id or name.")],
    requested_by: Annotated[
        str,
        typer.Option("--requested-by", help="Requester identity to store on the task."),
    ] = "user:local",
    priority: Annotated[
        str,
        typer.Option("--priority", help="Priority: low, normal, high, or urgent."),
    ] = "normal",
    mode: Annotated[
        str,
        typer.Option("--mode", help="Mode: plan, review, implement, or verify."),
    ] = "implement",
    constraint: Annotated[
        list[str] | None,
        typer.Option("--constraint", help="Task constraint. May be repeated."),
    ] = None,
    accepted_interpretation: Annotated[
        str | None,
        typer.Option("--accepted-interpretation", help="Accepted interpretation of the request."),
    ] = None,
    in_scope: Annotated[
        list[str] | None,
        typer.Option("--in-scope", help="In-scope work. May be repeated."),
    ] = None,
    out_of_scope: Annotated[
        list[str] | None,
        typer.Option("--out-of-scope", help="Out-of-scope work. May be repeated."),
    ] = None,
    allowed_autonomy: Annotated[
        list[str] | None,
        typer.Option("--allowed-autonomy", help="Autonomous action allowed. May be repeated."),
    ] = None,
    stop_condition: Annotated[
        list[str] | None,
        typer.Option("--stop-condition", help="Condition that should stop execution."),
    ] = None,
    scope_change_rule: Annotated[
        list[str] | None,
        typer.Option("--scope-change-rule", help="Rule for handling scope changes."),
    ] = None,
    expected_output: Annotated[
        list[str] | None,
        typer.Option("--expected-output", help="Expected output. May be repeated."),
    ] = None,
) -> None:
    """Create a task request for a registered project."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        registry = ProjectRegistry(store)
        profile = registry.get_project(project)
        if profile is None:
            raise typer.BadParameter(f"unknown project: {project}")
        task = create_task(
            store,
            title=title,
            objective=objective,
            project_id=profile.id,
            requested_by=requested_by,
            priority=_priority(priority),
            mode=_task_mode(mode),
            constraints=constraint,
            expected_outputs=expected_output,
        )
        intent_lock = IntentLockManager(store).create_for_task(
            task,
            accepted_interpretation=accepted_interpretation,
            in_scope=in_scope,
            out_of_scope=out_of_scope,
            allowed_autonomy=allowed_autonomy,
            stop_conditions=stop_condition,
            scope_change_rules=scope_change_rule,
        )
    finally:
        store.close()

    payload = {
        "task": task.model_dump(mode="json", by_alias=True),
        "intent_lock": intent_lock.model_dump(mode="json", by_alias=True),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@intent_app.command("show")
def intent_show(intent_or_task_id: str) -> None:
    """Show one persisted intent lock by intent lock id or task id."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        intent_lock = IntentLockManager(store).require(intent_or_task_id)
    except IntentLockNotFoundError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(
        json.dumps(intent_lock.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


@case_app.command("build")
def case_build(
    task_id: Annotated[str, typer.Argument(help="Task id to build a case file for.")],
    max_tokens: Annotated[
        int,
        typer.Option("--max-tokens", min=1, help="Approximate context budget."),
    ] = 24000,
    github: Annotated[
        bool,
        typer.Option("--github/--no-github", help="Load read-only GitHub context."),
    ] = True,
    discovery_include: Annotated[
        list[str] | None,
        typer.Option(
            "--discovery-include",
            help="One-off context discovery include override. May be repeated.",
        ),
    ] = None,
    discovery_exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--discovery-exclude",
            help="One-off context discovery exclude override. May be repeated.",
        ),
    ] = None,
) -> None:
    """Build and persist a deterministic case file for a task."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        github_adapter = _github_adapter() if github else None
        assembler = CaseFileAssembler(store, github_adapter=github_adapter)
        case_file = assembler.build(
            task_id,
            max_tokens=max_tokens,
            discovery_overrides=DiscoveryOverrides(
                include=tuple(discovery_include or ()),
                exclude=tuple(discovery_exclude or ()),
            ),
        )
    except (TaskNotFoundError, ProjectNotFoundError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(
        json.dumps(case_file.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


def _github_adapter() -> GitHubReadAdapter:
    config = GitHubConfig.from_env(dict(os.environ))
    return GitHubReadAdapter(GitHubClient(config))


@case_app.command("show")
def case_show(case_or_task_id: str) -> None:
    """Show one persisted case file by case id or task id."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        assembler = CaseFileAssembler(store)
        case_file = assembler.get(case_or_task_id) or assembler.latest_for_task(case_or_task_id)
    finally:
        store.close()

    if case_file is None:
        raise typer.BadParameter(f"unknown case file or task: {case_or_task_id}")
    typer.echo(
        json.dumps(case_file.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
    )


def _priority(value: str) -> Priority:
    if value not in {"low", "normal", "high", "urgent"}:
        raise typer.BadParameter(f"unsupported priority: {value}")
    return cast(Priority, value)


def _task_mode(value: str) -> TaskMode:
    if value not in {"plan", "review", "implement", "verify"}:
        raise typer.BadParameter(f"unsupported task mode: {value}")
    return cast(TaskMode, value)
