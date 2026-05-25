"""CommandResult helpers for skill package CLI/TUI projections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from craik.runtime.contract import CommandResult
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.skills.packages import (
    install_skill_package,
    list_skill_packages,
    set_skill_registry_entry_active,
)
from craik.runtime.store import LocalStore


def skills_overview_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return installed packages, registries, and skill proposal state."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        packages = store.list_skill_packages()
        registries = store.list_skill_registries()
        proposals = store.list_distilled_instruction_proposals()
    finally:
        store.close()
    return CommandResult(
        payload={
            "packages": [_payload(package) for package in packages],
            "registries": [_payload(registry) for registry in registries],
            "proposals": [_payload(proposal) for proposal in proposals],
        },
        shape="card_list",
        empty_state_message="No skill packages found.",
    )


def skills_install_result(path: Path, env: dict[str, str] | None = None) -> CommandResult:
    """Install a skill package manifest."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        package = install_skill_package(store, path)
    finally:
        store.close()
    return CommandResult(payload=_payload(package), shape="card")


def skills_list_result(
    *,
    scope: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return installed skill packages."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        packages = list_skill_packages(store, scope=scope)
    finally:
        store.close()
    return CommandResult(
        payload=[_payload(package) for package in packages],
        shape="card_list",
        empty_state_message="No skill packages found.",
    )


def skills_set_active_result(
    entry_id: str,
    *,
    active: bool,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Enable or disable one skill registry entry."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        registry = set_skill_registry_entry_active(store, entry_id, active=active)
    finally:
        store.close()
    if registry is None:
        raise ValueError(f"unknown skill registry entry: {entry_id}")
    return CommandResult(payload=_payload(registry), shape="card")


def skills_show_result(package_id: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return one installed skill package."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        package = store.get_skill_package(package_id)
    finally:
        store.close()
    if package is None:
        raise ValueError(f"unknown skill package: {package_id}")
    return CommandResult(payload=_payload(package), shape="card")


def skills_telemetry_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return redacted skill invocation telemetry inputs."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        contexts = store.list_skill_invocation_contexts()
    finally:
        store.close()
    return CommandResult(
        payload={
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
        },
        shape="card_list",
    )


def skills_proposals_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return reviewable learning-loop proposal sources."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        instruction_proposals = store.list_distilled_instruction_proposals()
    finally:
        store.close()
    return CommandResult(
        payload={
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
        },
        shape="card_list",
    )


def skills_eval_result(
    *,
    package_id: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return replay/eval readiness for skill promotion gates."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        packages = store.list_skill_packages()
    finally:
        store.close()
    filtered = [package for package in packages if package_id in {None, package.id}]
    return CommandResult(
        payload={
            "package_count": len(filtered),
            "eval_status": "no replay fixtures recorded",
            "items": [_payload(package) for package in filtered],
            "redacted": True,
        },
        shape="card_list",
    )


def skills_promote_result(proposal_id: str, *, dry_run: bool = True) -> CommandResult:
    """Return a skill promotion preview payload."""
    return CommandResult(
        payload={
            "proposal_id": proposal_id,
            "dry_run": dry_run,
            "approved": False,
            "reason": "skill promotion requires explicit approval, replay evidence, and receipts",
            "silent_promotion_allowed": False,
        },
        shape="card",
    )


def skills_rollback_result(package_id: str, *, dry_run: bool = True) -> CommandResult:
    """Return rollback posture for a skill package."""
    return CommandResult(
        payload={
            "package_id": package_id,
            "dry_run": dry_run,
            "rollback_ready": False,
            "reason": (
                "rollback requires a promoted version, prior version, "
                "replay context, and receipt"
            ),
        },
        shape="card",
    )


def skills_history_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return skill package and learning-loop receipt history."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
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
    return CommandResult(
        payload={
            "packages": [_payload(package) for package in packages],
            "learning_receipts": [
                receipt.model_dump(mode="json", by_alias=True) for receipt in receipts
            ],
            "redacted": True,
        },
        shape="card_list",
    )


def _payload(model: Any) -> dict[str, object]:
    return cast(dict[str, object], model.model_dump(mode="json", by_alias=True))
