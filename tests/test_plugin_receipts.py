import pytest
from pydantic import ValidationError

from craik.contracts.models import PluginReceipt
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _receipt(**overrides: object) -> PluginReceipt:
    payload = {
        "id": "plugin_receipt_docs_reconcile",
        "task_id": "task_docs_reconcile",
        "actor": "agent:codex",
        "plugin_descriptor_id": "plugin_docs_reconcile",
        "plugin_probation_id": "plugin_probation_docs_reconcile",
        "action": "docs.reconcile",
        "capability_grant_ids": ["grant_docs_write"],
        "trust_boundary": "project",
        "result": {
            "status": "passed",
            "summary": "Plugin action completed with redacted output.",
            "metadata": {"redacted": True},
        },
        "evidence_ids": ["evidence_readme_status"],
        "handoff_ids": ["handoff_docs_reconcile"],
        "redacted": True,
        "created_at": "2026-05-16T16:20:00Z",
    }
    payload.update(overrides)
    return PluginReceipt.model_validate(payload)


def test_plugin_receipt_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        receipt = _receipt()
        store.put_plugin_receipt(receipt)

        assert store.get_plugin_receipt(receipt.id) == receipt
        assert store.list_plugin_receipts() == [receipt]
    finally:
        store.close()


def test_plugin_receipt_supports_successful_failed_and_denied_results() -> None:
    successful = _receipt()
    failed = _receipt(
        id="plugin_receipt_failed",
        result={
            "status": "failed",
            "summary": "Plugin action failed after validation.",
            "metadata": {"redacted": True},
        },
    )
    denied = _receipt(
        id="plugin_receipt_denied",
        result={
            "status": "denied",
            "summary": "Plugin action denied by policy.",
            "metadata": {"policy": "strict"},
        },
    )

    assert successful.result.status == "passed"
    assert failed.result.status == "failed"
    assert denied.result.status == "denied"


def test_plugin_receipt_requires_redaction() -> None:
    with pytest.raises(ValidationError, match="must be redacted"):
        _receipt(redacted=False)

    with pytest.raises(ValidationError, match="must not mark output unredacted"):
        _receipt(
            result={
                "status": "passed",
                "summary": "Raw output.",
                "metadata": {"redacted": False},
            }
        )


def test_plugin_receipt_probation_link_is_optional_but_non_empty() -> None:
    without_probation = _receipt(plugin_probation_id=None)

    assert without_probation.plugin_probation_id is None

    with pytest.raises(ValidationError, match="probation ids"):
        _receipt(plugin_probation_id="")


def test_plugin_receipt_requires_grant_descriptor_evidence_and_handoff_links() -> None:
    with pytest.raises(ValidationError):
        _receipt(capability_grant_ids=[])

    with pytest.raises(ValidationError):
        _receipt(plugin_descriptor_id=None)

    with pytest.raises(ValidationError):
        _receipt(evidence_ids=[])

    with pytest.raises(ValidationError):
        _receipt(handoff_ids=[])
