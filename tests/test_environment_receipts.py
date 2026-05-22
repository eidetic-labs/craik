from datetime import UTC, datetime

from craik.runtime.environment_receipts import (
    EnvironmentReceiptContext,
    environment_receipt,
)

NOW = datetime(2026, 5, 16, 20, 30, tzinfo=UTC)


def _context() -> EnvironmentReceiptContext:
    return EnvironmentReceiptContext(
        task_id="task_environment",
        agent_session_id="agent_session_environment",
        policy_envelope_id="policy_environment",
        provider_id="provider_fixture_local",
        backend_id="sandbox_backend_local_fixture",
        route_id="mcp_route_provider_fixture",
        target_id="remote_target_fixture",
        command_ref="check_ruff",
        receipt_ids=["receipt_prior"],
    )


def test_environment_receipt_records_success_context() -> None:
    receipt = environment_receipt(
        receipt_id="receipt_environment_allowed",
        action="sandbox_action",
        context=_context(),
        actor="agent:codex",
        capability="shell.execute",
        policy_profile="strict",
        status="passed",
        reason="Local process request allowed.",
        summary="Sandbox action approved.",
        metadata={"backend_kind": "local_process"},
        created_at=NOW,
    )

    assert receipt.result.status == "passed"
    assert receipt.target == "sandbox_action:check_ruff"
    assert receipt.result.metadata["policy_envelope_id"] == "policy_environment"
    assert receipt.result.metadata["agent_session_id"] == "agent_session_environment"
    assert receipt.result.metadata["provider_id"] == "provider_fixture_local"
    assert receipt.result.metadata["backend_id"] == "sandbox_backend_local_fixture"
    assert receipt.result.metadata["route_id"] == "mcp_route_provider_fixture"
    assert receipt.result.metadata["target_id"] == "remote_target_fixture"
    assert receipt.result.metadata["command_ref"] == "check_ruff"
    assert receipt.result.metadata["backend_kind"] == "local_process"


def test_environment_receipt_records_denial_context() -> None:
    receipt = environment_receipt(
        receipt_id="receipt_environment_denied",
        action="denial",
        context=_context(),
        actor="agent:codex",
        capability="shell.remote.execute",
        policy_profile="strict",
        status="denied",
        reason="Remote shell execution requires a receipt.",
        summary="Remote shell action denied.",
        created_at=NOW,
    )

    assert receipt.result.status == "denied"
    assert receipt.capability == "shell.remote.execute"
    assert receipt.reason == "Remote shell execution requires a receipt."
    assert receipt.result.metadata["environment_action"] == "denial"
    assert receipt.result.metadata["receipt_ids"] == ["receipt_prior"]


def test_environment_receipt_redacts_environment_and_command_payloads() -> None:
    receipt = environment_receipt(
        receipt_id="receipt_environment_redacted",
        action="provider_action",
        context=_context(),
        actor="agent:codex",
        capability="model.chat",
        policy_profile="strict",
        status="passed",
        reason="Provider route selected.",
        summary="Provider action approved.",
        metadata={
            "env": {"TOKEN": "secret"},
            "environment_variables": {"API_KEY": "secret"},
            "credentials": {"password": "secret"},
            "command_payload": "uv run pytest",
            "raw_command": "ssh host uname -a",
            "stdout": "raw output",
            "stderr": "raw error",
            "api_token": "raw-token",
            "safe": "kept",
        },
        created_at=NOW,
    )

    assert receipt.redacted is True
    assert receipt.result.metadata["safe"] == "kept"
    assert "env" not in receipt.result.metadata
    assert "environment_variables" not in receipt.result.metadata
    assert "credentials" not in receipt.result.metadata
    assert "command_payload" not in receipt.result.metadata
    assert "raw_command" not in receipt.result.metadata
    assert "stdout" not in receipt.result.metadata
    assert "stderr" not in receipt.result.metadata
    assert "api_token" not in receipt.result.metadata
    assert "command_payload" in receipt.result.metadata["redacted_fields"]
