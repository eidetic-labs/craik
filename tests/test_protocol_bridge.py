import json
from datetime import UTC, datetime

from craik.runtime.agents.protocol_bridge import (
    AgentClientBridgeRequest,
    LocalAgentClientBridgeAdapter,
    decide_agent_client_bridge,
)


def _request(**overrides: object) -> AgentClientBridgeRequest:
    payload = {
        "id": "bridge_req_1",
        "client_name": "fixture-editor",
        "tool_name": "case.read",
        "capability": "file.read",
        "operator_subject": "operator-123",
        "policy_envelope_id": "policy_bridge",
        "capability_grant_id": "grant_bridge",
        "arguments": {"path": "README.md"},
    }
    payload.update(overrides)
    return AgentClientBridgeRequest.model_validate(payload)


def test_bridge_decision_allows_policy_bound_read_call() -> None:
    decision = decide_agent_client_bridge(_request())

    assert decision.allowed is True
    assert decision.status == "allowed"
    assert decision.required_controls == [
        "operator_auth",
        "policy_envelope",
        "capability_grant",
        "receipts",
        "redaction",
    ]


def test_bridge_decision_blocks_missing_auth_and_policy() -> None:
    missing_auth = decide_agent_client_bridge(_request(operator_subject=None))
    missing_policy = decide_agent_client_bridge(_request(policy_envelope_id=None))

    assert missing_auth.allowed is False
    assert missing_auth.reason == "operator authentication is required"
    assert missing_policy.allowed is False
    assert missing_policy.reason == "policy envelope is required"


def test_bridge_decision_blocks_instruction_elevation_and_unbounded_tools() -> None:
    authoritative = decide_agent_client_bridge(
        _request(accepts_authoritative_instructions=True)
    )
    unbounded = decide_agent_client_bridge(_request(unbounded_tool_access=True))

    assert authoritative.allowed is False
    assert authoritative.reason == "client instructions must not outrank Craik policy"
    assert unbounded.allowed is False
    assert unbounded.reason == "unbounded tool access is prohibited"


def test_bridge_write_calls_require_approval_and_emit_receipts() -> None:
    denied = LocalAgentClientBridgeAdapter().handle(
        _request(effect="write", capability="memory.write", tool_name="memory.propose")
    )
    assert denied.status == "blocked"
    assert denied.receipt is None
    assert denied.decision.reason == "write bridge calls require operator approval"

    allowed = LocalAgentClientBridgeAdapter().handle(
        _request(
            effect="write",
            capability="memory.write",
            tool_name="memory.propose",
            approval_id="approval_bridge",
            evidence_ids=["evidence_bridge"],
        ),
        now=datetime(2026, 5, 23, 6, 40, tzinfo=UTC),
    )

    assert allowed.status == "completed"
    assert allowed.receipt is not None
    assert allowed.receipt.capability == "memory.write"
    assert allowed.receipt.operator_subject == "operator-123"
    assert allowed.receipt.result.metadata["redacted"] is True
    assert "evidence_links" in allowed.decision.required_controls


def test_bridge_request_redacts_secret_like_arguments() -> None:
    request = _request(arguments={"prompt": "Bearer secretfixture12345", "token": "raw"})
    result = LocalAgentClientBridgeAdapter().handle(request)

    assert result.status == "completed"
    assert "secretfixture" not in json.dumps(request.model_dump(mode="json"))
    assert request.arguments["token"] == "[REDACTED]"
