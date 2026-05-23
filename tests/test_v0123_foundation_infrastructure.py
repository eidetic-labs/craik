from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import PolicyEnvelope, ShellInvocationReceipt
from craik.contracts.registry import CONTRACT_REGISTRY
from craik.runtime.auth.operator_modes import is_audit_reduced_mode
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.envelope import is_auto_approve_shape
from craik.runtime.store import LocalStore
from craik.runtime.store.integrity import contract_hmac, hmac_key_for_store
from craik.runtime.store.receipt_integrity import contract_receipt_hmac_status


def test_auto_approve_detection_supports_existing_policy_fields() -> None:
    policy = PolicyEnvelope(
        id="policy_auto",
        task_id="task_auto",
        actor="agent:test",
        profile="custom",
        allowed_capabilities=["*"],
        approval_required=[],
    )

    assert is_auto_approve_shape(policy) is True
    gated = policy.model_copy(update={"approval_required": ["shell"]})
    assert is_auto_approve_shape(gated) is False


def test_auto_approve_detection_supports_forward_compatible_shapes() -> None:
    assert is_auto_approve_shape({"approve_all_capabilities": True}) is True
    assert (
        is_auto_approve_shape(
            {
                "required_approval_capabilities": [],
                "allowlist": ["capability:*"],
            }
        )
        is True
    )
    assert (
        is_auto_approve_shape(
            {
                "per_capability_gates": {
                    "shell.execute": "auto",
                    "memory.write": {"mode": "auto"},
                }
            }
        )
        is True
    )
    assert is_auto_approve_shape({"per_capability_gates": {"shell.execute": "prompt"}}) is False


def test_shell_invocation_receipt_is_registered_and_hmac_inspectable(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        receipt = ShellInvocationReceipt(
            receipt_id="receipt_shell_echo",
            timestamp=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
            operator_subject="local-user:test",
            command="echo hello",
            exit_code=0,
            stdout_preview="hello\n",
            stderr_preview="",
            stdout_sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            stderr_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            working_directory="/tmp",
            duration_ms=12,
        )
        payload = receipt.model_dump(mode="json", by_alias=True)
        signed = receipt.model_copy(
            update={"receipt_hmac": contract_hmac(payload, hmac_key_for_store(store))}
        )

        assert CONTRACT_REGISTRY["craik.shell_invocation_receipt"] is ShellInvocationReceipt
        assert contract_receipt_hmac_status(store, receipt) == "unverified"
        assert contract_receipt_hmac_status(store, signed) == "verified"
        assert (
            contract_receipt_hmac_status(
                store,
                signed.model_copy(update={"command": "echo tampered"}),
            )
            == "tampered"
        )
    finally:
        store.close()


def test_audit_reduced_mode_tracks_operator_requirement() -> None:
    assert is_audit_reduced_mode({}) is True
    assert is_audit_reduced_mode({"CRAIK_OPERATOR_REQUIRED": "1"}) is False
