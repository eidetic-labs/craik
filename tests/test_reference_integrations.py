import pytest
from pydantic import ValidationError

from craik.contracts.models import ReferenceIntegration
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _integration(kind: str = "skill", **overrides: object) -> ReferenceIntegration:
    payload = {
        "id": f"reference_{kind}_docs_reconcile",
        "kind": kind,
        "name": f"Docs Reconcile {kind.title()} Reference",
        "description": "Safe reproducible reference integration fixture.",
        "skill_package_id": "skill_docs_reconcile" if kind == "skill" else None,
        "plugin_descriptor_id": "plugin_docs_reconcile" if kind == "plugin" else None,
        "adapter_package_id": "adapter_package_codex_fixture"
        if kind == "adapter"
        else None,
        "docs": ["docs/reference/skill-packages.md"],
        "fixture_paths": ["tests/fixtures/contracts/v0_1/contracts.json"],
        "check_commands": ["uv run --extra dev pytest tests/test_contracts.py"],
        "receipt_ids": ["plugin_receipt_docs_reconcile"] if kind == "plugin" else [],
        "compatibility_notes": ["Compatible with v0.6 reference contracts."],
        "safe_to_run_locally": True,
        "reproducible": True,
        "provenance_ids": ["evidence_readme_status"],
        "created_at": "2026-05-16T16:50:00Z",
    }
    payload.update(overrides)
    return ReferenceIntegration.model_validate(payload)


def test_reference_integration_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        integration = _integration()
        store.put_reference_integration(integration)

        assert store.get_reference_integration(integration.id) == integration
        assert store.list_reference_integrations() == [integration]
    finally:
        store.close()


def test_reference_integrations_cover_skill_plugin_and_adapter_paths() -> None:
    skill = _integration("skill")
    plugin = _integration("plugin")
    adapter = _integration("adapter")

    assert skill.skill_package_id == "skill_docs_reconcile"
    assert plugin.plugin_descriptor_id == "plugin_docs_reconcile"
    assert adapter.adapter_package_id == "adapter_package_codex_fixture"


def test_reference_integrations_require_matching_reference_ids() -> None:
    with pytest.raises(ValidationError, match="skill_package_id"):
        _integration("skill", skill_package_id=None)

    with pytest.raises(ValidationError, match="plugin_descriptor_id"):
        _integration("plugin", plugin_descriptor_id=None)

    with pytest.raises(ValidationError, match="adapter_package_id"):
        _integration("adapter", adapter_package_id=None)

    with pytest.raises(ValidationError, match="must not link plugin or adapter"):
        _integration("skill", plugin_descriptor_id="plugin_docs_reconcile")

    with pytest.raises(ValidationError, match="must not link skill or adapter"):
        _integration("plugin", skill_package_id="skill_docs_reconcile")

    with pytest.raises(ValidationError, match="must not link skill or plugin"):
        _integration("adapter", plugin_descriptor_id="plugin_docs_reconcile")


def test_plugin_reference_integrations_require_receipts() -> None:
    with pytest.raises(ValidationError, match="receipt_ids"):
        _integration("plugin", receipt_ids=[])


def test_reference_integrations_require_reproducible_artifacts() -> None:
    with pytest.raises(ValidationError):
        _integration(fixture_paths=[])

    with pytest.raises(ValidationError):
        _integration(check_commands=[])

    with pytest.raises(ValidationError, match="safe and reproducible"):
        _integration(safe_to_run_locally=False)

    with pytest.raises(ValidationError, match="safe and reproducible"):
        _integration(reproducible=False)


def test_reference_integration_rejects_unsafe_ids_and_docs() -> None:
    with pytest.raises(ValidationError, match="contract ids"):
        _integration(id="Reference.Integration")

    with pytest.raises(ValidationError, match="docs references"):
        _integration(docs=["file:///tmp/reference.md"])
