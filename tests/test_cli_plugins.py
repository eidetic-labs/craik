import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import (
    PluginCapabilityGrant,
    PluginDescriptor,
    PluginProbation,
    PluginReceipt,
)
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

runner = CliRunner()


def _put_operator_session(home: Path) -> None:
    ensure_craik_home({"CRAIK_HOME": str(home)})
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )


def test_plugins_install_cli_emits_single_command_result_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)
    manifest = tmp_path / "plugin.json"
    manifest.write_text(_descriptor().model_dump_json(), encoding="utf-8")

    result = runner.invoke(
        app,
        ["plugins", "install", str(manifest)],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exception is None, result.output
    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    payload = json.loads(result.stdout)
    assert payload["id"] == "plugin_docs_reconcile"
    assert payload["runtime_authority"] is False


def test_plugins_grant_cli_emits_single_command_result_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)

    result = runner.invoke(
        app,
        [
            "plugins",
            "grant",
            "plugin_docs_reconcile",
            "--operation",
            "read",
            "--target",
            "docs/**",
            "--expiry",
            "2026-06-16T16:30:00Z",
            "--task",
            "task_docs_reconcile",
            "--policy",
            "policy_docs_reconcile",
            "--evidence",
            "evidence_readme_status",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exception is None, result.output
    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    payload = json.loads(result.stdout)
    assert payload["plugin_descriptor_id"] == "plugin_docs_reconcile"
    assert payload["approved_by"] == "operator-123"


def test_plugins_probation_review_cli_emits_single_command_result_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)
    _seed_probation(home)

    result = runner.invoke(
        app,
        [
            "plugins",
            "probation",
            "review",
            "plugin_probation_docs_reconcile",
            "--evidence",
            "evidence_readme_status",
            "--decide",
            "pass",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exception is None, result.output
    assert result.exit_code == 0
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    payload = json.loads(result.stdout)
    assert payload["status"] == "promoted"
    assert payload["decision"]["decided_by"] == "operator-123"


def test_plugins_grants_and_receipts_list_emit_single_json_documents(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)
    _seed_grant_and_receipt(home)

    grants = runner.invoke(
        app,
        ["plugins", "grants", "list", "--plugin", "plugin_docs_reconcile"],
        env={"CRAIK_HOME": str(home)},
    )
    receipts = runner.invoke(
        app,
        ["plugins", "receipts", "list", "--plugin", "plugin_docs_reconcile"],
        env={"CRAIK_HOME": str(home)},
    )

    assert grants.exception is None, grants.output
    assert grants.exit_code == 0
    assert grants.stdout.strip().startswith("[")
    assert grants.stdout.strip().endswith("]")
    assert json.loads(grants.stdout)[0]["id"] == "plugin_grant_docs_reconcile"
    assert receipts.exception is None, receipts.output
    assert receipts.exit_code == 0
    assert receipts.stdout.strip().startswith("[")
    assert receipts.stdout.strip().endswith("]")
    assert json.loads(receipts.stdout)[0]["id"] == "plugin_receipt_docs_reconcile"


def _seed_probation(home: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_plugin_probation(_probation())
    finally:
        store.close()


def _seed_grant_and_receipt(home: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_plugin_capability_grant(_grant())
        store.put_plugin_receipt(_receipt())
    finally:
        store.close()


def _descriptor() -> PluginDescriptor:
    return PluginDescriptor.model_validate(
        {
            "id": "plugin_docs_reconcile",
            "name": "Docs Reconcile Plugin",
            "plugin_version": "0.1.0",
            "description": "Adds governed docs reconciliation workflow entrypoints.",
            "publisher": "Eidetic Labs",
            "trust_boundary": "project",
            "entrypoints": [
                {
                    "id": "entry_workflow",
                    "kind": "workflow",
                    "path": "plugin.py:run",
                    "description": "Runs the docs reconciliation workflow.",
                }
            ],
            "capabilities": [
                {
                    "capability": "repo.read",
                    "description": "Read project source and documentation files.",
                    "required": True,
                    "grant_required": True,
                    "risk": "medium",
                    "operations": ["read"],
                    "targets": ["repo"],
                }
            ],
            "docs": ["README.md"],
            "compatibility": {
                "craik_versions": ["0.12.8"],
                "python_versions": ["3.12"],
                "platforms": ["darwin", "linux"],
                "status": "supported",
            },
            "security_notes": ["Runtime authority requires explicit grants."],
            "runtime_authority": False,
            "created_at": "2026-05-16T15:45:00Z",
        }
    )


def _probation() -> PluginProbation:
    return PluginProbation.model_validate(
        {
            "id": "plugin_probation_docs_reconcile",
            "plugin_descriptor_id": "plugin_docs_reconcile",
            "policy_envelope_id": "policy_docs_reconcile",
            "status": "probationary",
            "criteria": [
                {
                    "name": "security_review",
                    "required": True,
                    "passed": False,
                    "summary": "Review plugin security posture.",
                    "evidence_ids": ["evidence_readme_status"],
                }
            ],
            "compatibility_check_ids": ["freshness_github_state"],
            "evidence_ids": ["evidence_readme_status"],
            "receipt_ids": ["receipt_runner_fixture"],
            "decision": None,
            "expires_at": "2026-06-16T16:10:00Z",
            "durable_trust_granted": False,
            "created_at": "2026-05-16T16:10:00Z",
        }
    )


def _grant() -> PluginCapabilityGrant:
    return PluginCapabilityGrant.model_validate(
        {
            "id": "plugin_grant_docs_reconcile",
            "task_id": "task_docs_reconcile",
            "plugin_descriptor_id": "plugin_docs_reconcile",
            "policy_envelope_id": "policy_docs_reconcile",
            "capability": "repo.write.docs",
            "target": {"repo": "eidetic-labs/craik", "paths": ["docs/**"], "metadata": {}},
            "operations": ["read", "write"],
            "status": "allowed",
            "approval_required": True,
            "approved_by": "user:maintainer",
            "expires_at": "2026-06-16T16:30:00Z",
            "reason": "Allow docs reconciliation plugin to update docs.",
            "evidence_ids": ["evidence_readme_status"],
            "created_at": "2026-05-16T16:30:00Z",
        }
    )


def _receipt() -> PluginReceipt:
    return PluginReceipt.model_validate(
        {
            "id": "plugin_receipt_docs_reconcile",
            "task_id": "task_docs_reconcile",
            "actor": "agent:fixture",
            "plugin_descriptor_id": "plugin_docs_reconcile",
            "plugin_probation_id": "plugin_probation_docs_reconcile",
            "action": "docs.reconcile",
            "capability_grant_ids": ["plugin_grant_docs_reconcile"],
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
    )
