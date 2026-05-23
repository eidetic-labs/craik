"""Agent/client protocol bridge decisions and first local adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from craik.contracts.models import CapabilityReceipt, CraikModel, ReceiptResult
from craik.runtime.policy.redaction import redact

BridgeDecisionStatus = Literal["allowed", "blocked", "review_required"]
BridgeToolEffect = Literal["read", "write"]


class AgentClientBridgeRequest(CraikModel):
    """Candidate tool call from an editor or client bridge."""

    id: str
    client_name: str
    tool_name: str
    capability: str
    effect: BridgeToolEffect = "read"
    arguments: dict[str, Any] = Field(default_factory=dict)
    operator_subject: str | None = None
    policy_envelope_id: str | None = None
    capability_grant_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    accepts_authoritative_instructions: bool = False
    unbounded_tool_access: bool = False
    redacted: bool = True

    @model_validator(mode="after")
    def validate_bridge_request(self) -> AgentClientBridgeRequest:
        """Reject obviously unsafe bridge payloads before decision logic."""
        redacted_arguments = redact(self.arguments)
        if redacted_arguments.redacted and self.redacted:
            self.arguments = (
                redacted_arguments.value if isinstance(redacted_arguments.value, dict) else {}
            )
        return self


class AgentClientBridgeDecision(CraikModel):
    """Security decision for one bridge request."""

    status: BridgeDecisionStatus
    allowed: bool
    request_id: str
    reason: str
    required_controls: list[str] = Field(default_factory=list)
    receipt_required: bool = True


class AgentClientBridgeResult(CraikModel):
    """Adapter result for an allowed bridge request."""

    request_id: str
    status: Literal["completed", "blocked"]
    decision: AgentClientBridgeDecision
    receipt: CapabilityReceipt | None = None
    output: dict[str, Any] = Field(default_factory=dict)


def decide_agent_client_bridge(
    request: AgentClientBridgeRequest,
) -> AgentClientBridgeDecision:
    """Decide whether an agent/client bridge request can execute."""
    controls = _required_controls(request)
    if not request.operator_subject:
        return _blocked(request, "operator authentication is required", controls)
    if not request.policy_envelope_id:
        return _blocked(request, "policy envelope is required", controls)
    if not request.capability_grant_id:
        return _blocked(request, "capability grant is required", controls)
    if request.accepts_authoritative_instructions:
        return _blocked(
            request,
            "client instructions must not outrank Craik policy",
            controls,
        )
    if request.unbounded_tool_access:
        return _blocked(request, "unbounded tool access is prohibited", controls)
    if not request.redacted:
        return _blocked(request, "bridge input and output must be redacted", controls)
    if request.effect == "write" and not request.approval_id:
        return _blocked(request, "write bridge calls require operator approval", controls)
    return AgentClientBridgeDecision(
        status="allowed",
        allowed=True,
        request_id=request.id,
        reason=(
            "bridge request satisfies operator auth, policy, grant, receipt, "
            "and redaction controls"
        ),
        required_controls=controls,
        receipt_required=True,
    )


class LocalAgentClientBridgeAdapter:
    """First local adapter for client protocol bridge smoke tests."""

    adapter_id = "craik.local_client_protocol_bridge"
    adapter_version = "0.12.0"

    def handle(
        self,
        request: AgentClientBridgeRequest,
        *,
        now: datetime | None = None,
    ) -> AgentClientBridgeResult:
        """Handle a bridge request, returning a receipt only for allowed calls."""
        decision = decide_agent_client_bridge(request)
        if not decision.allowed:
            return AgentClientBridgeResult(
                request_id=request.id,
                status="blocked",
                decision=decision,
                output={"reason": decision.reason, "redacted": True},
            )
        timestamp = now or datetime.now(UTC)
        output = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "tool_name": request.tool_name,
            "capability": request.capability,
            "effect": request.effect,
            "redacted": True,
        }
        receipt = CapabilityReceipt(
            id=f"bridge_receipt_{_fingerprint(request.id)}",
            task_id=request.id,
            actor=self.adapter_id,
            capability=request.capability,
            target=request.tool_name,
            policy_profile="strict",
            reason="agent/client protocol bridge tool call",
            result=ReceiptResult(
                status="passed",
                summary="Bridge tool call completed under Craik controls.",
                metadata=output,
            ),
            operator_subject=request.operator_subject,
            created_at=timestamp,
            redacted=True,
        )
        return AgentClientBridgeResult(
            request_id=request.id,
            status="completed",
            decision=decision,
            receipt=receipt,
            output=output,
        )


def _blocked(
    request: AgentClientBridgeRequest,
    reason: str,
    controls: list[str],
) -> AgentClientBridgeDecision:
    return AgentClientBridgeDecision(
        status="blocked",
        allowed=False,
        request_id=request.id,
        reason=reason,
        required_controls=controls,
        receipt_required=True,
    )


def _required_controls(request: AgentClientBridgeRequest) -> list[str]:
    controls = ["operator_auth", "policy_envelope", "capability_grant", "receipts", "redaction"]
    if request.effect == "write":
        controls.append("operator_approval")
    if request.evidence_ids:
        controls.append("evidence_links")
    return controls


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def bridge_decision_payload(decision: AgentClientBridgeDecision) -> dict[str, Any]:
    """Return a JSON-ready bridge decision payload."""
    payload = json.loads(decision.model_dump_json())
    return payload if isinstance(payload, dict) else {}
