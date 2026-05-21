import pytest
from pydantic import ValidationError

from craik.contracts.models import SkillRegistry
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _entry(
    entry_id: str,
    *,
    scope: str,
    precedence: int,
    active: bool = True,
) -> dict[str, object]:
    return {
        "id": entry_id,
        "skill_package_id": "skill_docs_reconcile",
        "scope": scope,
        "project_id": "project_stigmem" if scope == "project" else None,
        "source_path": ".craik/skills/docs-reconcile/SKILL.md"
        if scope == "project"
        else "~/.craik/skills/docs-reconcile/SKILL.md",
        "trust_boundary": "project" if scope == "project" else "user",
        "precedence": precedence,
        "active": active,
        "provenance_ids": ["evidence_readme_status"],
        "declared_by": "agent:orchestrator",
        "created_at": "2026-05-16T16:00:00Z",
    }


def _registry(**overrides: object) -> SkillRegistry:
    entries = [
        _entry("skill_entry_project_docs", scope="project", precedence=0),
        _entry("skill_entry_global_docs", scope="global", precedence=10),
    ]
    payload = {
        "id": "skill_registry_project_stigmem",
        "project_id": "project_stigmem",
        "entries": entries,
        "active_entry_ids": [
            "skill_entry_project_docs",
            "skill_entry_global_docs",
        ],
        "precedence_order": [
            "skill_entry_project_docs",
            "skill_entry_global_docs",
        ],
        "created_at": "2026-05-16T16:00:00Z",
    }
    payload.update(overrides)
    return SkillRegistry.model_validate(payload)


def test_skill_registry_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        registry = _registry()
        store.put_skill_registry(registry)

        assert store.get_skill_registry(registry.id) == registry
        assert store.list_skill_registries() == [registry]
    finally:
        store.close()


def test_skill_registry_supports_project_and_global_entries() -> None:
    registry = _registry()

    assert [entry.scope for entry in registry.entries] == ["project", "global"]
    assert registry.entries[0].trust_boundary == "project"
    assert registry.entries[1].trust_boundary == "user"


def test_skill_registry_requires_scope_project_boundaries() -> None:
    with pytest.raises(ValidationError, match="project_id"):
        _registry(
            entries=[
                {
                    **_entry("project_missing", scope="project", precedence=0),
                    "project_id": None,
                }
            ]
        )

    with pytest.raises(ValidationError, match="must not set project_id"):
        _registry(
            entries=[
                {
                    **_entry("global_with_project", scope="global", precedence=0),
                    "project_id": "project_stigmem",
                }
            ]
        )


def test_skill_registry_source_paths_are_project_confined() -> None:
    absolute = {
        **_entry("skill_entry_project_docs", scope="project", precedence=0),
        "source_path": "/tmp/skill/SKILL.md",
    }
    traversal = {
        **_entry("skill_entry_project_docs", scope="project", precedence=0),
        "source_path": "../skill/SKILL.md",
    }

    with pytest.raises(ValidationError, match="confined relative path"):
        _registry(entries=[absolute], active_entry_ids=["skill_entry_project_docs"])

    with pytest.raises(ValidationError, match="confined relative path"):
        _registry(entries=[traversal], active_entry_ids=["skill_entry_project_docs"])


def test_skill_registry_rejects_inactive_active_entry() -> None:
    inactive = _entry("skill_entry_inactive", scope="project", precedence=0, active=False)

    with pytest.raises(ValidationError, match="inactive skill entry ids"):
        _registry(entries=[inactive], active_entry_ids=["skill_entry_inactive"])


def test_skill_registry_requires_active_entries_to_be_listed() -> None:
    with pytest.raises(ValidationError, match="active skill entries missing"):
        _registry(active_entry_ids=["skill_entry_project_docs"])


def test_skill_registry_rejects_unknown_precedence_entries() -> None:
    with pytest.raises(ValidationError, match="unknown precedence"):
        _registry(precedence_order=["skill_entry_missing"])


def test_skill_registry_rejects_inactive_precedence_entries() -> None:
    active = _entry("skill_entry_project_docs", scope="project", precedence=0)
    inactive = _entry("skill_entry_inactive", scope="global", precedence=10, active=False)

    with pytest.raises(ValidationError, match="inactive skill entry ids in precedence_order"):
        _registry(
            entries=[active, inactive],
            active_entry_ids=["skill_entry_project_docs"],
            precedence_order=["skill_entry_project_docs", "skill_entry_inactive"],
        )


def test_skill_registry_project_entries_outrank_global_entries() -> None:
    entries = [
        _entry("skill_entry_project_docs", scope="project", precedence=20),
        _entry("skill_entry_global_docs", scope="global", precedence=10),
    ]

    with pytest.raises(ValidationError, match="project-scoped skills"):
        _registry(entries=entries)


def test_skill_registry_requires_provenance() -> None:
    entry = {**_entry("skill_entry_project_docs", scope="project", precedence=0)}
    entry["provenance_ids"] = []

    with pytest.raises(ValidationError):
        _registry(entries=[entry], active_entry_ids=["skill_entry_project_docs"])
