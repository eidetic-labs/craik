"""Skill package CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from craik.cli import skills_app
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.skills.packages import (
    install_skill_package,
    list_skill_packages,
    set_skill_registry_entry_active,
)
from craik.runtime.store import LocalStore


@skills_app.command("install")
def skills_install(
    path: Annotated[Path, typer.Argument(help="Skill package JSON manifest.")],
) -> None:
    """Install a skill package manifest."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        package = install_skill_package(store, path)
    finally:
        store.close()
    _print(package)


@skills_app.command("list")
def skills_list(
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Optional registry scope: project or global."),
    ] = None,
) -> None:
    """List installed skill packages."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        packages = list_skill_packages(store, scope=scope)
    finally:
        store.close()
    typer.echo(json.dumps([_payload(package) for package in packages], indent=2, sort_keys=True))


@skills_app.command("enable")
def skills_enable(
    entry_id: Annotated[str, typer.Argument(help="Skill registry entry id.")],
) -> None:
    """Enable a skill registry entry."""
    _operator_identity()
    _set_active(entry_id, active=True)


@skills_app.command("disable")
def skills_disable(
    entry_id: Annotated[str, typer.Argument(help="Skill registry entry id.")],
) -> None:
    """Disable a skill registry entry."""
    _operator_identity()
    _set_active(entry_id, active=False)


@skills_app.command("show")
def skills_show(package_id: Annotated[str, typer.Argument(help="Skill package id.")]) -> None:
    """Show one installed skill package."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        package = store.get_skill_package(package_id)
    finally:
        store.close()
    if package is None:
        raise typer.BadParameter(f"unknown skill package: {package_id}")
    _print(package)


def _set_active(entry_id: str, *, active: bool) -> None:
    store = LocalStore.from_env()
    try:
        store.initialize()
        registry = set_skill_registry_entry_active(store, entry_id, active=active)
    finally:
        store.close()
    if registry is None:
        raise typer.BadParameter(f"unknown skill registry entry: {entry_id}")
    _print(registry)


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        raise typer.BadParameter("active operator session required; run craik auth login") from None
    return session.subject


def _payload(model: object) -> dict[str, object]:
    return model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined,no-any-return]


def _print(model: object) -> None:
    typer.echo(json.dumps(_payload(model), indent=2, sort_keys=True))
