import pytest
from pydantic import ValidationError

from craik.contracts.models import SkillPackage
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _package(**overrides: object) -> SkillPackage:
    payload = {
        "id": "skill_docs_reconcile",
        "name": "Docs Reconcile",
        "package_version": "0.1.0",
        "description": "Review docs against implementation state.",
        "entrypoints": [
            {
                "id": "entry_prompt",
                "kind": "prompt",
                "path": "SKILL.md",
                "description": "Skill instructions.",
                "expected_input_schemas": ["craik.case_file"],
                "expected_output_schemas": ["craik.worker_result"],
            }
        ],
        "docs": ["SKILL.md"],
        "assets": ["fixtures/example.md"],
        "expected_input_schemas": ["craik.case_file"],
        "expected_output_schemas": ["craik.worker_result"],
        "context_requirements": [
            {
                "schema_name": "craik.case_file",
                "required": True,
                "trust_boundary": "project",
                "missing_context_behavior": "reject",
                "summary": "Task case file required before invoking the skill.",
                "evidence_ids": ["evidence_skill_package"],
            }
        ],
        "provenance_ids": ["evidence_skill_package"],
        "runtime_authority": False,
        "created_at": "2026-05-16T15:30:00Z",
    }
    payload.update(overrides)
    return SkillPackage.model_validate(payload)


def test_skill_package_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        package = _package()
        store.put_skill_package(package)

        assert store.get_skill_package(package.id) == package
        assert store.list_skill_packages() == [package]
        assert package.runtime_authority is False
    finally:
        store.close()


def test_skill_package_requires_entrypoints() -> None:
    with pytest.raises(ValidationError):
        _package(entrypoints=[])


def test_skill_package_requires_version_and_docs() -> None:
    with pytest.raises(ValidationError, match="semantic-version-like"):
        _package(package_version="preview")

    with pytest.raises(ValidationError, match="semantic-version-like"):
        _package(package_version="1.2")

    with pytest.raises(ValidationError, match="semantic-version-like"):
        _package(package_version="1.2.x")

    with pytest.raises(ValidationError, match="require docs"):
        _package(docs=[])


def test_skill_package_accepts_semantic_version_suffixes() -> None:
    prerelease = _package(id="skill_docs_reconcile_beta", package_version="1.2.3-beta.1")
    build = _package(id="skill_docs_reconcile_build", package_version="1.2.3+build.7")

    assert prerelease.package_version == "1.2.3-beta.1"
    assert build.package_version == "1.2.3+build.7"


def test_skill_package_declares_expected_input_context() -> None:
    with pytest.raises(ValidationError, match="require context requirements"):
        _package(context_requirements=[])
