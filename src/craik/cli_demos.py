"""Demo CLI commands."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from craik.cli import demo_app
from craik.runtime.agents.demo import PersistentAgentLaunchDemo
from craik.runtime.github import GitHubClient, GitHubConfig, GitHubReadAdapter
from craik.runtime.projects.demos import StigmemDocsDemo
from craik.runtime.projects.demos_provider import ProviderBackedStigmemDocsDemo
from craik.runtime.projects.project_registry import NotGitRepositoryError
from craik.runtime.providers.model_providers import (
    ModelProviderNotFoundError,
)
from craik.runtime.secrets import SecretNotFoundError
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import ProjectNotFoundError, TaskNotFoundError
from craik.runtime.work.handoffs import HandoffContextError


@demo_app.command("stigmem-docs")
def demo_stigmem_docs(
    repo_path: Annotated[
        Path,
        typer.Option("--repo-path", help="Path inside the Stigmem Git repository."),
    ] = Path("."),
    project_name: Annotated[
        str,
        typer.Option("--project-name", help="Project name to register for the demo."),
    ] = "Stigmem",
    stigmem_url: Annotated[
        str | None,
        typer.Option("--stigmem-url", envvar="CRAIK_STIGMEM_URL", help="Stigmem node URL."),
    ] = None,
    stigmem_api_key: Annotated[
        str | None,
        typer.Option(
            "--stigmem-api-key",
            envvar="CRAIK_STIGMEM_API_KEY",
            help="Bearer API key. Prefer CRAIK_STIGMEM_API_KEY.",
        ),
    ] = None,
    github: Annotated[
        bool,
        typer.Option("--github/--no-github", help="Load read-only GitHub context."),
    ] = True,
    provider_id: Annotated[
        list[str] | None,
        typer.Option(
            "--provider-id",
            help=(
                "Provider id to exercise through the deterministic demo runner. "
                "Repeat to override the default OpenAI and Anthropic run."
            ),
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(
            "--provider",
            help=(
                "Run one provider-backed demo path and surface model findings. "
                "Set CRAIK_LIVE=1 for live transport; otherwise fixture transport is used."
            ),
        ),
    ] = None,
    max_tokens: Annotated[
        int,
        typer.Option("--max-tokens", min=1, help="Approximate case-file context budget."),
    ] = 24000,
) -> None:
    """Run the Stigmem documentation reconciliation demo."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        github_adapter = _github_adapter() if github else None
        if provider and provider_id:
            raise typer.BadParameter("use either --provider or --provider-id, not both")
        if provider:
            result = ProviderBackedStigmemDocsDemo(
                store,
                github_adapter=github_adapter,
            ).run(
                repo_path=repo_path,
                project_name=project_name,
                stigmem_url=stigmem_url,
                stigmem_api_key=stigmem_api_key,
                github=github,
                provider_id=provider,
                live_enabled=_env_flag("CRAIK_LIVE"),
                max_tokens=max_tokens,
            )
        else:
            result = StigmemDocsDemo(
                store,
                github_adapter=github_adapter,
            ).run(
                repo_path=repo_path,
                project_name=project_name,
                stigmem_url=stigmem_url,
                stigmem_api_key=stigmem_api_key,
                github=github,
                provider_ids=tuple(provider_id) if provider_id else None,
                max_tokens=max_tokens,
            )
    except (
        NotGitRepositoryError,
        TaskNotFoundError,
        ProjectNotFoundError,
        HandoffContextError,
        ModelProviderNotFoundError,
        SecretNotFoundError,
    ) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()

    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@demo_app.command("persistent-agent")
def demo_persistent_agent(
    repo_path: Annotated[
        Path,
        typer.Option("--repo-path", help="Path inside the Git repository for the demo."),
    ] = Path("."),
    project_name: Annotated[
        str,
        typer.Option("--project-name", help="Project name to register for the demo."),
    ] = "Persistent Agent Demo",
    provider_id: Annotated[
        list[str] | None,
        typer.Option(
            "--provider-id",
            help="Provider id to exercise. Repeat to override the default provider set.",
        ),
    ] = None,
) -> None:
    """Run the deterministic persistent agent launch demo."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        result = PersistentAgentLaunchDemo(store).run(
            repo_path=repo_path,
            project_name=project_name,
            provider_ids=tuple(provider_id) if provider_id else None,
        )
    except (NotGitRepositoryError, ModelProviderNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        store.close()
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


def _github_adapter() -> GitHubReadAdapter:
    config = GitHubConfig.from_env(dict(os.environ))
    return GitHubReadAdapter(GitHubClient(config))


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
