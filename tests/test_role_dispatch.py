import pytest

from craik.contracts.models import PolicyEnvelope
from craik.runtime.runners.role_dispatch import (
    RoleDispatchDeniedError,
    RoleDispatchUnknownRoleError,
    default_agent_roles,
    dispatch_role,
    role_dispatch_receipt,
)


def test_default_agent_roles_define_specialist_runner_assignments() -> None:
    roles = default_agent_roles(policy_envelope_id="policy_task")

    assert set(roles) == {
        "orchestrator",
        "implementer",
        "verifier",
        "adversarial_reviewer",
        "policy_reviewer",
        "docs_reviewer",
        "memory_curator",
        "adjudicator",
    }
    assert roles["implementer"].runner_id == "provider_openai_chat"
    assert roles["adversarial_reviewer"].runner_id == "provider_anthropic_messages"
    assert roles["adjudicator"].authority == ["adjudicate"]


def test_dispatch_role_records_runner_and_receipt_metadata() -> None:
    policy = _policy().model_copy(update={"allowed_agent_role_kinds": ["docs_reviewer"]})

    dispatch = dispatch_role(policy=policy, role_kind="docs_reviewer")

    assert dispatch.role.kind == "docs_reviewer"
    assert dispatch.runner.runner.id == "provider_openai_chat"
    assert dispatch.receipt.capability == "role.dispatch"
    assert dispatch.receipt.result.status == "passed"
    assert dispatch.receipt.result.metadata["role_kind"] == "docs_reviewer"
    assert dispatch.receipt.result.metadata["runner_id"] == "provider_openai_chat"


def test_dispatch_role_rejects_unknown_role() -> None:
    with pytest.raises(RoleDispatchUnknownRoleError, match="unknown role"):
        dispatch_role(policy=_policy(), role_id="role_missing")


def test_dispatch_role_honors_policy_allowed_role_kinds() -> None:
    policy = _policy().model_copy(update={"allowed_agent_role_kinds": ["verifier"]})
    receipt = role_dispatch_receipt(
        policy=policy,
        role=default_agent_roles(policy_envelope_id=policy.id)["docs_reviewer"],
    )

    assert receipt.result.status == "denied"
    assert "not allowed by policy" in receipt.reason
    with pytest.raises(RoleDispatchDeniedError, match="not allowed by policy"):
        dispatch_role(policy=policy, role_kind="docs_reviewer")


def test_dispatch_role_rejects_default_policy_without_role_allowlist() -> None:
    policy = _policy()
    receipt = role_dispatch_receipt(
        policy=policy,
        role=default_agent_roles(policy_envelope_id=policy.id)["docs_reviewer"],
    )

    assert receipt.result.status == "denied"
    assert "does not define allowed agent roles" in receipt.reason
    with pytest.raises(RoleDispatchDeniedError, match="does not define allowed agent roles"):
        dispatch_role(policy=policy, role_kind="docs_reviewer")


def test_dispatch_role_rejects_runner_override_without_policy_capability() -> None:
    policy = _policy().model_copy(update={"allowed_agent_role_kinds": ["docs_reviewer"]})

    with pytest.raises(RoleDispatchDeniedError, match="runner override is not allowed"):
        dispatch_role(
            policy=policy,
            role_kind="docs_reviewer",
            runner_id="provider_anthropic_messages",
        )


def test_dispatch_role_allows_policy_gated_runner_override() -> None:
    policy = _policy().model_copy(
        update={
            "allowed_agent_role_kinds": ["docs_reviewer"],
            "allowed_capabilities": [
                "repo.read",
                "memory.read",
                "receipt.write",
                "role.runner.override",
            ],
        }
    )

    dispatch = dispatch_role(
        policy=policy,
        role_kind="docs_reviewer",
        runner_id="provider_anthropic_messages",
    )

    assert dispatch.role.runner_id == "provider_anthropic_messages"


def _policy() -> PolicyEnvelope:
    return PolicyEnvelope(
        id="policy_task",
        task_id="task_docs",
        actor="agent:test",
        profile="strict",
        allowed_capabilities=["repo.read", "memory.read", "receipt.write"],
        denied_capabilities=["repo.write", "memory.write"],
        approval_required=[],
        verification_required=[],
    )
