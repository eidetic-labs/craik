import pytest
from pydantic import ValidationError

from craik.contracts.models import AdapterPackage
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _package(**overrides: object) -> AdapterPackage:
    payload = {
        "id": "adapter_package_codex_fixture",
        "name": "Codex Fixture Adapter",
        "package_version": "0.1.0",
        "adapter": "codex",
        "description": "Fixture adapter package metadata.",
        "entrypoints": [
            {
                "id": "adapter_module",
                "kind": "module",
                "path": "craik.adapters.codex:CodexAdapter",
                "description": "Adapter implementation entrypoint.",
            }
        ],
        "capability_surfaces": ["prompt.read", "result.structured"],
        "compatibility": {
            "craik_versions": ["0.6.0"],
            "runner_modes": ["prompt-handoff"],
            "python_versions": ["3.12"],
            "platforms": ["darwin", "linux"],
            "notes": "Fixture compatibility metadata.",
        },
        "runner_metadata_ids": ["runner_fixture"],
        "plugin_descriptor_ids": ["plugin_docs_reconcile"],
        "docs": ["docs/reference/codex-runner-adapter.md"],
        "provenance_ids": ["evidence_readme_status"],
        "version_constraints": ["craik>=0.6,<0.7"],
        "created_at": "2026-05-16T16:40:00Z",
    }
    payload.update(overrides)
    return AdapterPackage.model_validate(payload)


def test_adapter_package_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        package = _package()
        store.put_adapter_package(package)

        assert store.get_adapter_package(package.id) == package
        assert store.list_adapter_packages() == [package]
    finally:
        store.close()


def test_adapter_package_requires_metadata_and_entrypoints() -> None:
    with pytest.raises(ValidationError):
        _package(entrypoints=[])

    with pytest.raises(ValidationError, match="semantic-version-like"):
        _package(package_version="preview")

    with pytest.raises(ValidationError, match="semantic-version-like"):
        _package(package_version="1.2")


def test_adapter_package_requires_compatibility() -> None:
    with pytest.raises(ValidationError):
        _package(compatibility={"craik_versions": ["0.6.0"], "runner_modes": []})

    with pytest.raises(ValidationError, match="craik_versions"):
        _package(
            compatibility={
                "craik_versions": ["0.6"],
                "runner_modes": ["prompt-handoff"],
                "python_versions": ["3.12"],
                "platforms": ["darwin"],
            }
        )

    with pytest.raises(ValidationError, match="python_versions"):
        _package(
            compatibility={
                "craik_versions": ["0.6.0"],
                "runner_modes": ["prompt-handoff"],
                "platforms": ["darwin"],
            }
        )

    with pytest.raises(ValidationError, match="platforms"):
        _package(
            compatibility={
                "craik_versions": ["0.6.0"],
                "runner_modes": ["prompt-handoff"],
                "python_versions": ["3.12"],
            }
        )


def test_adapter_package_requires_capability_surfaces_docs_and_provenance() -> None:
    with pytest.raises(ValidationError):
        _package(capability_surfaces=[])

    with pytest.raises(ValidationError):
        _package(docs=[])

    with pytest.raises(ValidationError):
        _package(provenance_ids=[])


def test_adapter_package_rejects_unsafe_ids_and_docs() -> None:
    with pytest.raises(ValidationError, match="contract ids"):
        _package(id="Adapter.Package")

    with pytest.raises(ValidationError, match="docs references"):
        _package(docs=["http://example.com/adapter"])
