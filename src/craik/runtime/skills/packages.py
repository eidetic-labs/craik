"""Runtime capture points for v0.6 skill package contracts."""

from __future__ import annotations

import json
from pathlib import Path

from craik.contracts.models import SkillInvocationContext, SkillPackage, SkillRegistry
from craik.runtime.policy.text import sanitize_runtime_text
from craik.runtime.store import LocalStore


def install_skill_package(store: LocalStore, manifest_path: Path) -> SkillPackage:
    """Load and persist a skill package contract from a JSON manifest."""
    package = SkillPackage.model_validate(_load_json(manifest_path))
    store.put_skill_package(package)
    return package


def record_skill_registry(store: LocalStore, registry: SkillRegistry) -> SkillRegistry:
    """Persist a skill registry update."""
    store.put_skill_registry(registry)
    return registry


def record_skill_invocation_context(
    store: LocalStore,
    context: SkillInvocationContext,
) -> SkillInvocationContext:
    """Persist a redacted skill invocation context after package validation."""
    package = store.get_skill_package(context.skill_package_id)
    if package is not None:
        package.validate_invocation_context(context)
    store.put_skill_invocation_context(context)
    return context


def list_skill_packages(store: LocalStore, *, scope: str | None = None) -> list[SkillPackage]:
    """List persisted skill packages, optionally filtered through registry scope."""
    if scope is None:
        return store.list_skill_packages()
    package_ids = {
        entry.skill_package_id
        for registry in store.list_skill_registries()
        for entry in registry.entries
        if entry.scope == scope and entry.active
    }
    return [package for package in store.list_skill_packages() if package.id in package_ids]


def render_skill_invocation_context(context: SkillInvocationContext) -> list[str]:
    """Render a skill invocation context with sanitized text fields."""
    lines = [
        f"Skill Invocation Context: {context.id}",
        f"Skill package: {context.skill_package_id}",
        "Inputs:",
    ]
    for context_input in context.inputs:
        lines.append(
            f"- {context_input.schema_name}: {sanitize_runtime_text(context_input.summary)}"
        )
    lines.append("Outputs:")
    for context_output in context.outputs:
        lines.append(
            f"- {context_output.schema_name}: {sanitize_runtime_text(context_output.summary)}"
        )
    if context.omissions:
        lines.append("Omissions:")
        for context_omission in context.omissions:
            reason = sanitize_runtime_text(context_omission.reason)
            lines.append(
                f"- {context_omission.schema_name}: {reason}"
            )
    return lines


def set_skill_registry_entry_active(
    store: LocalStore,
    entry_id: str,
    *,
    active: bool,
) -> SkillRegistry | None:
    """Enable or disable a skill registry entry in the latest registry containing it."""
    registries = sorted(
        store.list_skill_registries(),
        key=lambda item: item.created_at,
        reverse=True,
    )
    for registry in registries:
        entries = []
        changed = False
        for entry in registry.entries:
            if entry.id == entry_id:
                entry = entry.model_copy(update={"active": active})
                changed = True
            entries.append(entry)
        if changed:
            active_ids = [entry.id for entry in entries if entry.active]
            precedence = [
                entry_id for entry_id in registry.precedence_order if entry_id in active_ids
            ]
            updated = registry.model_copy(
                update={
                    "entries": entries,
                    "active_entry_ids": active_ids,
                    "precedence_order": precedence,
                }
            )
            store.put_skill_registry(updated)
            return updated
    return None


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
