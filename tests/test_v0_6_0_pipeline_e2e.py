import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.contracts.models import (
    CapabilityTarget,
    PluginCapabilityGrant,
    PluginDescriptor,
    SkillInvocationContext,
    SkillRegistry,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.runners.adapter_packages import install_adapter_package
from craik.runtime.skills.authorization import (
    PluginAuthorizationError,
    authorize_plugin_operation,
)
from craik.runtime.skills.packages import (
    install_skill_package,
    record_skill_invocation_context,
    record_skill_registry,
    render_skill_invocation_context,
)
from craik.runtime.skills.plugins import (
    probation_from_descriptor,
    record_plugin_capability_grant,
    record_plugin_probation,
    record_plugin_receipt,
    review_plugin_probation,
)
from craik.runtime.skills.references import install_reference_integration
from craik.runtime.store import LocalStore, LocalStoreCorruptError


def test_v0_6_0_pipeline_wires_contracts_to_runtime_capture_points(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        skill_package = install_skill_package(
            store,
            _write_json(tmp_path, "skill.json", _skill_package()),
        )
        registry = record_skill_registry(store, SkillRegistry.model_validate(_skill_registry()))
        context = record_skill_invocation_context(
            store,
            SkillInvocationContext.model_validate(_skill_context()),
        )

        descriptor = install_plugin_descriptor_for_test(store, tmp_path)
        probation = record_plugin_probation(
            store,
            probation_from_descriptor(
                probation_id="plugin_probation_docs_reconcile",
                descriptor=descriptor,
                policy_envelope_id="policy_docs_reconcile",
                evidence_ids=["evidence_plugin_descriptor"],
                created_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
            ),
        )
        grant = record_plugin_capability_grant(
            store,
            PluginCapabilityGrant.model_validate(_plugin_grant()),
        )

        with pytest.raises(PluginAuthorizationError, match="durable trust"):
            authorize_plugin_operation(
                store,
                plugin_id=descriptor.id,
                operation="write",
                target=CapabilityTarget(repo="eidetic-labs/craik", paths=["docs/**"]),
                operator_identity="user:maintainer",
                now=datetime(2026, 5, 21, 12, 5, tzinfo=UTC),
            )

        promoted = review_plugin_probation(
            store,
            probation.id,
            decision="pass",
            decided_by="user:maintainer",
            rationale="Reference checks passed.",
            evidence_ids=["evidence_plugin_descriptor"],
        )
        assert promoted.durable_trust_granted is True
        authorized = authorize_plugin_operation(
            store,
            plugin_id=descriptor.id,
            operation="write",
            target=CapabilityTarget(repo="eidetic-labs/craik", paths=["docs/**"]),
            operator_identity="user:maintainer",
            now=datetime(2026, 5, 21, 12, 10, tzinfo=UTC),
        )
        assert authorized.id == grant.id

        receipt = record_plugin_receipt(
            store,
            receipt_id="plugin_receipt_docs_reconcile_e2e",
            task_id="task_docs_reconcile",
            actor="plugin:docs-reconcile",
            plugin_descriptor_id=descriptor.id,
            plugin_probation_id=promoted.id,
            action="docs.reconcile",
            capability_grant_ids=[grant.id],
            trust_boundary="project",
            status="passed",
            summary="Wrote docs with token=secret-fixture",
            metadata={"api_key": "secret-fixture", "redacted": False},
            evidence_ids=["evidence_plugin_descriptor"],
            handoff_ids=["handoff_docs_reconcile"],
            created_at=datetime(2026, 5, 21, 12, 15, tzinfo=UTC),
        )
        adapter = install_adapter_package(
            store,
            _write_json(tmp_path, "adapter.json", _adapter_package()),
        )
        reference = install_reference_integration(
            store,
            _write_json(tmp_path, "reference.json", _reference_integration(receipt.id)),
        )

        assert skill_package.id == "skill_docs_reconcile"
        assert registry.active_entry_ids == ["skill_entry_project_docs"]
        assert context.skill_package_id == skill_package.id
        assert receipt.receipt_hmac
        assert receipt.result.metadata["redacted"] is True
        assert "secret-fixture" not in json.dumps(receipt.model_dump(mode="json"))
        assert adapter.id == "adapter_package_codex_fixture"
        assert reference.receipt_ids == [receipt.id]

        with pytest.raises(PluginAuthorizationError, match="no live capability grant"):
            authorize_plugin_operation(
                store,
                plugin_id=descriptor.id,
                operation="write",
                target=CapabilityTarget(repo="eidetic-labs/craik", paths=["src/**"]),
                operator_identity="user:maintainer",
                now=datetime(2026, 5, 21, 12, 10, tzinfo=UTC),
            )
    finally:
        store.close()


def test_plugin_probation_and_receipt_hmac_detect_tamper(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        descriptor = install_plugin_descriptor_for_test(store, tmp_path)
        probation = record_plugin_probation(
            store,
            probation_from_descriptor(
                probation_id="plugin_probation_docs_reconcile",
                descriptor=descriptor,
                policy_envelope_id="policy_docs_reconcile",
                evidence_ids=["evidence_plugin_descriptor"],
            ),
        )
        receipt = record_plugin_receipt(
            store,
            receipt_id="plugin_receipt_docs_reconcile_e2e",
            task_id="task_docs_reconcile",
            actor="plugin:docs-reconcile",
            plugin_descriptor_id=descriptor.id,
            plugin_probation_id=probation.id,
            action="docs.reconcile",
            capability_grant_ids=["plugin_grant_docs_reconcile"],
            trust_boundary="project",
            status="passed",
            summary="Completed.",
            metadata={},
            evidence_ids=["evidence_plugin_descriptor"],
            handoff_ids=["handoff_docs_reconcile"],
        )

        _tamper_record(store, "plugin_probations", probation.id, "evidence_ids", ["tampered"])
        with pytest.raises(LocalStoreCorruptError, match="plugin probation"):
            store.get_plugin_probation(probation.id)

        _tamper_record(store, "plugin_receipts", receipt.id, "actor", "plugin:tampered")
        with pytest.raises(LocalStoreCorruptError, match="plugin receipt"):
            store.get_plugin_receipt(receipt.id)
        read_result = store.get_plugin_receipt_with_verification(receipt.id)
        assert read_result is not None
        assert read_result.hmac_status == "tampered"
        assert read_result.receipt.actor == "plugin:tampered"
    finally:
        store.close()


def test_skill_invocation_context_rendering_sanitizes_text() -> None:
    context = SkillInvocationContext.model_validate(
        {
            **_skill_context(),
            "inputs": [
                {
                    "schema_name": "craik.case_file",
                    "contract_id": "case_docs_reconcile",
                    "trust_boundary": "project",
                    "summary": "safe\n## injected `heading`",
                }
            ],
        }
    )

    rendered = "\n".join(render_skill_invocation_context(context))

    assert "##" not in rendered
    assert "\\`heading\\`" in rendered
    assert "safe # # injected" in rendered


def install_plugin_descriptor_for_test(store: LocalStore, tmp_path: Path) -> PluginDescriptor:
    from craik.runtime.skills.plugins import install_plugin_descriptor

    return install_plugin_descriptor(
        store,
        _write_json(tmp_path, "plugin.json", _plugin_descriptor()),
    )


def _tamper_record(store: LocalStore, kind: str, record_id: str, field: str, value: object) -> None:
    record = store.get_contract(f"craik.{kind.removesuffix('s')}", record_id)
    if record is None:
        if kind == "plugin_probations":
            record = store.get_plugin_probation(record_id)
        elif kind == "plugin_receipts":
            record = store.get_plugin_receipt(record_id)
    assert record is not None
    payload = record.model_dump(mode="json", by_alias=True)
    payload[field] = value
    with store.transaction() as connection:
        connection.execute(
            "UPDATE records SET payload_json = ? WHERE kind = ? AND id = ?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), kind, record_id),
        )


def _write_json(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _skill_package() -> dict[str, object]:
    return {
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
            }
        ],
        "docs": ["SKILL.md"],
        "expected_input_schemas": ["craik.case_file"],
        "context_requirements": [
            {
                "schema_name": "craik.case_file",
                "required": True,
                "trust_boundary": "project",
                "missing_context_behavior": "reject",
                "summary": "Case file required.",
            }
        ],
        "created_at": "2026-05-21T12:00:00Z",
    }


def _skill_registry() -> dict[str, object]:
    return {
        "id": "skill_registry_project_docs",
        "project_id": "project_docs",
        "entries": [
            {
                "id": "skill_entry_project_docs",
                "skill_package_id": "skill_docs_reconcile",
                "scope": "project",
                "project_id": "project_docs",
                "source_path": ".craik/skills/docs/SKILL.md",
                "trust_boundary": "project",
                "precedence": 0,
                "active": True,
                "provenance_ids": ["evidence_plugin_descriptor"],
                "declared_by": "user:maintainer",
                "created_at": "2026-05-21T12:00:00Z",
            }
        ],
        "active_entry_ids": ["skill_entry_project_docs"],
        "precedence_order": ["skill_entry_project_docs"],
        "created_at": "2026-05-21T12:00:00Z",
    }


def _skill_context() -> dict[str, object]:
    return {
        "id": "skill_context_docs",
        "task_id": "task_docs_reconcile",
        "skill_package_id": "skill_docs_reconcile",
        "policy_envelope_id": "policy_docs_reconcile",
        "inputs": [
            {
                "schema_name": "craik.case_file",
                "contract_id": "case_docs_reconcile",
                "required": True,
                "trust_boundary": "project",
                "summary": "Case file.",
            }
        ],
        "outputs": [
            {
                "schema_name": "craik.worker_result",
                "contract_id": "worker_docs_reconcile",
                "required": True,
                "produced": True,
                "summary": "Worker result.",
            }
        ],
        "created_at": "2026-05-21T12:00:00Z",
    }


def _plugin_descriptor() -> dict[str, object]:
    return {
        "id": "plugin_docs_reconcile",
        "name": "Docs Reconcile Plugin",
        "plugin_version": "0.1.0",
        "description": "Governed docs reconciliation plugin.",
        "publisher": "Eidetic Labs",
        "trust_boundary": "project",
        "entrypoints": [
            {
                "id": "entry_workflow",
                "kind": "workflow",
                "path": "plugin.py:run",
                "description": "Run docs reconciliation.",
            }
        ],
        "capabilities": [
            {
                "capability": "repo.write.docs",
                "description": "Write docs.",
                "risk": "high",
                "operations": ["write"],
                "targets": ["docs/**"],
            }
        ],
        "docs": ["docs/plugin.md"],
        "compatibility": {
            "craik_versions": ["0.6.0"],
            "python_versions": ["3.12"],
            "platforms": ["darwin", "linux"],
            "status": "supported",
        },
        "security_notes": ["Requires explicit grants."],
        "skill_package_ids": ["skill_docs_reconcile"],
        "created_at": "2026-05-21T12:00:00Z",
    }


def _plugin_grant() -> dict[str, object]:
    return {
        "id": "plugin_grant_docs_reconcile",
        "task_id": "task_docs_reconcile",
        "plugin_descriptor_id": "plugin_docs_reconcile",
        "policy_envelope_id": "policy_docs_reconcile",
        "capability": "repo.write.docs",
        "target": {"repo": "eidetic-labs/craik", "paths": ["docs/**"]},
        "operations": ["write"],
        "status": "allowed",
        "approval_required": True,
        "approved_by": "user:maintainer",
        "expires_at": "2026-05-22T12:00:00Z",
        "reason": "Docs update approved.",
        "evidence_ids": ["evidence_plugin_descriptor"],
        "created_at": "2026-05-21T12:00:00Z",
    }


def _adapter_package() -> dict[str, object]:
    return {
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
                "description": "Adapter entrypoint.",
            }
        ],
        "capability_surfaces": ["prompt.read"],
        "compatibility": {
            "craik_versions": ["0.6.0"],
            "runner_modes": ["prompt-handoff"],
            "python_versions": ["3.12"],
            "platforms": ["darwin", "linux"],
        },
        "docs": ["docs/reference/codex-runner-adapter.md"],
        "provenance_ids": ["evidence_plugin_descriptor"],
        "created_at": "2026-05-21T12:00:00Z",
    }


def _reference_integration(receipt_id: str) -> dict[str, object]:
    return {
        "id": "reference_plugin_docs_reconcile",
        "kind": "plugin",
        "name": "Docs Reconcile Plugin Reference",
        "description": "Safe reproducible plugin reference.",
        "plugin_descriptor_id": "plugin_docs_reconcile",
        "docs": ["docs/reference/plugin-receipts.md"],
        "fixture_paths": ["tests/fixtures/contracts/v0_1/contracts.json"],
        "check_commands": ["uv run pytest tests/test_v0_6_0_pipeline_e2e.py"],
        "receipt_ids": [receipt_id],
        "compatibility_notes": ["Compatible with v0.6 runtime capture."],
        "provenance_ids": ["evidence_plugin_descriptor"],
        "created_at": "2026-05-21T12:00:00Z",
    }
