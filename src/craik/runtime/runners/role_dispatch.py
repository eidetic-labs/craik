"""Policy-aware role dispatch for specialist runners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from craik.contracts.models import (
    AgentRole,
    AgentRoleAuthority,
    AgentRoleKind,
    CapabilityReceipt,
    PolicyEnvelope,
    ReceiptResult,
    ReceiptStatus,
    RunnerCapabilityMatrix,
)
from craik.runtime.runners.runners import get_runner_capability_matrix

DEFAULT_ROLE_RUNNERS: dict[AgentRoleKind, str] = {
    "orchestrator": "provider_openai_chat",
    "implementer": "provider_openai_chat",
    "verifier": "provider_openai_responses",
    "adversarial_reviewer": "provider_anthropic_messages",
    "policy_reviewer": "provider_openai_responses",
    "docs_reviewer": "provider_openai_chat",
    "memory_curator": "provider_openai_chat",
    "adjudicator": "provider_anthropic_messages",
}

ROLE_AUTHORITIES: dict[AgentRoleKind, list[str]] = {
    "orchestrator": ["coordinate"],
    "implementer": ["implement"],
    "verifier": ["review"],
    "adversarial_reviewer": ["review"],
    "policy_reviewer": ["review"],
    "docs_reviewer": ["review"],
    "memory_curator": ["review"],
    "adjudicator": ["adjudicate"],
}

ROLE_OUTPUTS: dict[AgentRoleKind, list[str]] = {
    "orchestrator": ["craik.handoff"],
    "implementer": ["craik.worker_result", "craik.handoff"],
    "verifier": ["craik.review_result"],
    "adversarial_reviewer": ["craik.review_result"],
    "policy_reviewer": ["craik.review_result"],
    "docs_reviewer": ["craik.review_result"],
    "memory_curator": ["craik.memory_proposal"],
    "adjudicator": ["craik.adjudication_outcome"],
}


class RoleDispatchError(RuntimeError):
    """Base error for role dispatch failures."""


class RoleDispatchDeniedError(RoleDispatchError):
    """Raised when policy blocks a role dispatch."""


class RoleDispatchUnknownRoleError(RoleDispatchError):
    """Raised when a requested specialist role cannot be resolved."""


@dataclass(frozen=True)
class RoleDispatch:
    """Resolved role and runner assignment."""

    role: AgentRole
    runner: RunnerCapabilityMatrix
    receipt: CapabilityReceipt


def default_agent_roles(
    *,
    policy_envelope_id: str | None = None,
    runner_overrides: dict[AgentRoleKind, str] | None = None,
) -> dict[AgentRoleKind, AgentRole]:
    """Return the built-in role catalog for v0.3.0 specialist dispatch."""
    runners = {**DEFAULT_ROLE_RUNNERS, **(runner_overrides or {})}
    return {
        kind: AgentRole(
            id=f"role_{kind}",
            kind=kind,
            name=kind.replace("_", " ").title(),
            description=f"Default {kind.replace('_', ' ')} specialist role.",
            runner_id=runners[kind],
            runner_mode=get_runner_capability_matrix(runners[kind]).runner.mode,
            authority=cast(list[AgentRoleAuthority], ROLE_AUTHORITIES[kind]),
            allowed_capabilities=_role_capabilities(kind),
            denied_capabilities=_role_denials(kind),
            policy_envelope_id=policy_envelope_id,
            expected_input_schemas=["craik.case_file", "craik.task_request"],
            expected_output_schemas=ROLE_OUTPUTS[kind],
        )
        for kind in DEFAULT_ROLE_RUNNERS
    }


def dispatch_role(
    *,
    policy: PolicyEnvelope,
    role_kind: AgentRoleKind | None = None,
    role_id: str | None = None,
    roles: list[AgentRole] | None = None,
    runner_id: str | None = None,
) -> RoleDispatch:
    """Resolve and policy-check one role dispatch."""
    role = _resolve_role(
        policy=policy,
        role_kind=role_kind,
        role_id=role_id,
        roles=roles,
        runner_id=runner_id,
    )
    receipt = role_dispatch_receipt(policy=policy, role=role)
    if receipt.result.status == "denied":
        raise RoleDispatchDeniedError(receipt.reason)
    if role.runner_id is None:
        raise RoleDispatchUnknownRoleError(f"role {role.id} does not define a runner")
    try:
        runner = get_runner_capability_matrix(role.runner_id)
    except KeyError as error:
        raise RoleDispatchUnknownRoleError(str(error)) from None
    return RoleDispatch(role=role, runner=runner, receipt=receipt)


def role_dispatch_receipt(
    *,
    policy: PolicyEnvelope,
    role: AgentRole,
    actor: str = "runner:orchestrator",
) -> CapabilityReceipt:
    """Build the receipt that records one role dispatch decision."""
    allowed, reason = _role_allowed(policy, role)
    status: ReceiptStatus = "passed" if allowed else "denied"
    return CapabilityReceipt(
        id=f"receipt_{policy.task_id}_role_dispatch_{role.kind}",
        task_id=policy.task_id,
        actor=actor,
        capability="role.dispatch",
        target=role.id,
        policy_profile=policy.profile,
        fail_open=policy.fail_open,
        reason=reason,
        result=ReceiptResult(
            status=status,
            summary=reason,
            metadata={
                "role_id": role.id,
                "role_kind": role.kind,
                "runner_id": role.runner_id,
                "runner_mode": role.runner_mode,
            },
        ),
        redacted=True,
        created_at=datetime.now(UTC),
    )


def _resolve_role(
    *,
    policy: PolicyEnvelope,
    role_kind: AgentRoleKind | None,
    role_id: str | None,
    roles: list[AgentRole] | None,
    runner_id: str | None,
) -> AgentRole:
    catalog = roles or list(default_agent_roles(policy_envelope_id=policy.id).values())
    matches = [
        role
        for role in catalog
        if (role_id is not None and role.id == role_id)
        or (role_kind is not None and role.kind == role_kind)
    ]
    if not matches:
        requested = role_id or role_kind or "<missing>"
        raise RoleDispatchUnknownRoleError(f"unknown role: {requested}")
    role = matches[0]
    if runner_id is None:
        return role
    return role.model_copy(update={"runner_id": runner_id})


def _role_allowed(policy: PolicyEnvelope, role: AgentRole) -> tuple[bool, str]:
    if policy.allowed_agent_role_ids is not None and role.id not in policy.allowed_agent_role_ids:
        return False, f"role id {role.id} is not allowed by policy {policy.id}"
    if (
        policy.allowed_agent_role_kinds is not None
        and role.kind not in policy.allowed_agent_role_kinds
    ):
        return False, f"role kind {role.kind} is not allowed by policy {policy.id}"
    denied = sorted(set(role.allowed_capabilities).intersection(policy.denied_capabilities))
    if denied:
        return False, f"role {role.id} requests capabilities denied by policy: {', '.join(denied)}"
    return True, f"role {role.id} dispatched to runner {role.runner_id}"


def _role_capabilities(kind: AgentRoleKind) -> list[str]:
    if kind == "implementer":
        return ["repo.read", "repo.write.local", "receipt.write"]
    if kind == "memory_curator":
        return ["memory.read", "memory.propose", "receipt.write"]
    if kind == "orchestrator":
        return ["repo.read", "memory.read", "receipt.write"]
    return ["repo.read", "memory.read", "receipt.write"]


def _role_denials(kind: AgentRoleKind) -> list[str]:
    if kind in {"verifier", "adversarial_reviewer", "policy_reviewer", "docs_reviewer"}:
        return ["repo.write", "memory.write"]
    if kind == "memory_curator":
        return ["repo.write"]
    return []
