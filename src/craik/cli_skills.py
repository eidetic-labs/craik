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
    _operator_identity()
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
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        package = store.get_skill_package(package_id)
    finally:
        store.close()
    if package is None:
        raise typer.BadParameter(f"unknown skill package: {package_id}")
    _print(package)


@skills_app.command("telemetry")
def skills_telemetry() -> None:
    """Summarize redacted skill invocation telemetry inputs."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        contexts = store.list_skill_invocation_contexts()
    finally:
        store.close()
    payload = {
        "telemetry_count": len(contexts),
        "items": [
            {
                "id": context.id,
                "skill_package_id": context.skill_package_id,
                "task_id": context.task_id,
                "policy_envelope_id": context.policy_envelope_id,
                "receipt_ids": context.receipt_ids,
                "redacted": True,
            }
            for context in contexts
        ],
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@skills_app.command("proposals")
def skills_proposals() -> None:
    """List reviewable learning-loop proposal sources."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        instruction_proposals = store.list_distilled_instruction_proposals()
    finally:
        store.close()
    payload = {
        "proposal_count": len(instruction_proposals),
        "items": [
            {
                "id": proposal.id,
                "status": proposal.promotion_status,
                "category": proposal.category,
                "source_id": proposal.source_id,
                "provenance_ids": proposal.provenance_ids,
                "evidence_ids": proposal.evidence_ids,
                "redacted": True,
            }
            for proposal in instruction_proposals
        ],
        "silent_promotion_allowed": False,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@skills_app.command("eval")
def skills_eval(
    package_id: Annotated[str | None, typer.Option("--package-id")] = None,
) -> None:
    """Report replay/eval readiness for skill promotion gates."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        packages = store.list_skill_packages()
    finally:
        store.close()
    filtered = [package for package in packages if package_id in {None, package.id}]
    payload = {
        "package_count": len(filtered),
        "eval_status": "no replay fixtures recorded",
        "items": [_payload(package) for package in filtered],
        "redacted": True,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@skills_app.command("promote")
def skills_promote(
    proposal_id: Annotated[str, typer.Argument(help="Proposal id to review for promotion.")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
) -> None:
    """Preview a skill promotion decision; promotion remains approval-gated."""
    _operator_identity()
    payload = {
        "proposal_id": proposal_id,
        "dry_run": dry_run,
        "approved": False,
        "reason": "skill promotion requires explicit approval, replay evidence, and receipts",
        "silent_promotion_allowed": False,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@skills_app.command("rollback")
def skills_rollback(
    package_id: Annotated[str, typer.Argument(help="Skill package id.")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
) -> None:
    """Preview rollback posture for a skill package."""
    _operator_identity()
    payload = {
        "package_id": package_id,
        "dry_run": dry_run,
        "rollback_ready": False,
        "reason": (
            "rollback requires a promoted version, prior version, replay context, and receipt"
        ),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@skills_app.command("history")
def skills_history() -> None:
    """Show skill package and learning-loop receipt history."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        packages = store.list_skill_packages()
        receipts = [
            receipt
            for receipt in store.list_receipts()
            if receipt.result.metadata.get("learning_action") is not None
        ]
    finally:
        store.close()
    payload = {
        "packages": [_payload(package) for package in packages],
        "learning_receipts": [
            receipt.model_dump(mode="json", by_alias=True) for receipt in receipts
        ],
        "redacted": True,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


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
