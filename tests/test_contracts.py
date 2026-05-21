import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from craik.contracts.models import SCHEMA_VERSION
from craik.contracts.registry import CONTRACT_REGISTRY, schema_names

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "contracts" / "v0_1" / "contracts.json"


@pytest.fixture(scope="module")
def fixtures() -> dict[str, dict[str, Any]]:
    return json.loads(FIXTURE_PATH.read_text())


def test_all_registered_contracts_have_valid_fixtures(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    assert set(fixtures) == set(schema_names())

    for name, model in CONTRACT_REGISTRY.items():
        parsed = model.model_validate(fixtures[name])
        assert parsed.model_dump(mode="json", by_alias=True)["schema"] == name


def test_contract_fixtures_round_trip_json(fixtures: dict[str, dict[str, Any]]) -> None:
    for name, model in CONTRACT_REGISTRY.items():
        parsed = model.model_validate(fixtures[name])
        reparsed = model.model_validate_json(parsed.model_dump_json(by_alias=True))
        assert reparsed == parsed


def test_contract_fixtures_pin_schema_version(fixtures: dict[str, dict[str, Any]]) -> None:
    for payload in fixtures.values():
        assert payload["version"] == SCHEMA_VERSION


def test_capability_receipt_auth_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.capability_receipt"])
    payload.update(
        {
            "auth_profile_id": "openai:work",
            "auth_kind": "api-key",
            "auth_identity_hash": "a" * 64,
        }
    )

    parsed = CONTRACT_REGISTRY["craik.capability_receipt"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["auth_profile_id"] == "openai:work"
    assert dumped["auth_kind"] == "api-key"
    assert dumped["auth_identity_hash"] == "a" * 64


def test_capability_receipt_integrity_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.capability_receipt"])
    payload["previous_receipt_hash"] = "a" * 64

    parsed = CONTRACT_REGISTRY["craik.capability_receipt"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["previous_receipt_hash"] == "a" * 64
    assert len(dumped["self_hash"]) == 64

    dumped["reason"] = "tampered"
    with pytest.raises(ValidationError, match="hash did not match"):
        CONTRACT_REGISTRY["craik.capability_receipt"].model_validate(dumped)


def test_capability_receipt_operator_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.capability_receipt"])
    payload.update(
        {
            "operator_subject": "operator-123",
            "operator_issuer": "https://issuer.example.test",
            "operator_email": "operator@example.test",
            "operator_groups": ["platform"],
        }
    )

    parsed = CONTRACT_REGISTRY["craik.capability_receipt"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["operator_subject"] == "operator-123"
    assert dumped["operator_issuer"] == "https://issuer.example.test"
    assert dumped["operator_email"] == "operator@example.test"
    assert dumped["operator_groups"] == ["platform"]


def test_policy_envelope_operator_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.policy_envelope"])
    payload.update(
        {
            "required_operator": True,
            "allowed_operator_groups": ["prod-deploy"],
            "allowed_operator_subjects": ["operator-123"],
            "required_operator_issuer": "https://issuer.example.test",
            "allowed_credential_kinds": ["secret-ref"],
            "allowed_credential_profiles": ["openai:prod-*"],
            "allowed_agent_role_kinds": ["verifier"],
            "allowed_agent_role_ids": ["role_verifier"],
        }
    )

    parsed = CONTRACT_REGISTRY["craik.policy_envelope"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["required_operator"] is True
    assert dumped["allowed_operator_groups"] == ["prod-deploy"]
    assert dumped["allowed_operator_subjects"] == ["operator-123"]
    assert dumped["required_operator_issuer"] == "https://issuer.example.test"
    assert dumped["allowed_credential_kinds"] == ["secret-ref"]
    assert dumped["allowed_credential_profiles"] == ["openai:prod-*"]
    assert dumped["allowed_agent_role_kinds"] == ["verifier"]
    assert dumped["allowed_agent_role_ids"] == ["role_verifier"]


def test_instruction_registration_contracts_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    registration = CONTRACT_REGISTRY["craik.instruction_source_registration"].model_validate(
        fixtures["craik.instruction_source_registration"]
    )
    receipt = CONTRACT_REGISTRY["craik.instruction_registry_receipt"].model_validate(
        fixtures["craik.instruction_registry_receipt"]
    )

    registration_payload = registration.model_dump(mode="json", by_alias=True)
    receipt_payload = receipt.model_dump(mode="json", by_alias=True)

    assert registration_payload["source_id"] == "instruction_source_agents_md"
    assert registration_payload["registered_by"] == "agent:orchestrator"
    assert receipt_payload["registration_id"] == registration_payload["id"]
    assert receipt_payload["capability"] == "instructions.register"


def test_instruction_approval_contract_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    proposal_payload = dict(fixtures["craik.distilled_instruction_proposal"])
    proposal_payload.update(
        {
            "promotion_status": "governing",
            "promoted_constraint_id": "constraint_distilled_instruction_agents_boundary",
            "decided_by": "user:maintainer",
            "decided_at": "2026-05-15T22:31:00Z",
        }
    )
    review_payload = dict(fixtures["craik.instruction_promotion_review"])
    review_payload.update(
        {
            "override_stale": True,
            "override_contradiction": True,
            "override_rationale": "Operator reviewed stale conflict manually.",
        }
    )

    proposal = CONTRACT_REGISTRY["craik.distilled_instruction_proposal"].model_validate(
        proposal_payload
    )
    review = CONTRACT_REGISTRY["craik.instruction_promotion_review"].model_validate(review_payload)

    assert proposal.promotion_status == "governing"
    dumped_review = review.model_dump(mode="json", by_alias=True)
    assert dumped_review["override_stale"] is True
    assert dumped_review["override_contradiction"] is True
    assert dumped_review["override_rationale"] == "Operator reviewed stale conflict manually."


def test_case_file_distillation_section_round_trips(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.case_file"])
    payload["distillations"] = [
        {
            "id": "distilled_instruction_agents_rule",
            "constraint_id": "constraint_distilled_instruction_agents_rule",
            "source_id": "instruction_source_agents_md",
            "snapshot_id": "instruction_snapshot_agents_md",
            "category": "command",
            "statement": "Run tests before merge.",
            "provenance": [
                {
                    "id": "provenance_agents_rule",
                    "path": "AGENTS.md",
                    "start_line": 1,
                    "end_line": 1,
                    "summary": "Run tests before merge.",
                }
            ],
            "approval_receipt": {
                "id": "promotion_review_distilled_instruction_agents_rule",
                "decision": "approved",
                "decided_by": "user:maintainer",
            },
        }
    ]

    parsed = CONTRACT_REGISTRY["craik.case_file"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["distillations"][0]["id"] == "distilled_instruction_agents_rule"
    assert dumped["distillations"][0]["approval_receipt"]["decision"] == "approved"


def test_compiled_prompt_distillation_section_round_trips(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.compiled_prompt"])
    payload["distillations"] = [
        {
            "id": "distilled_instruction_agents_boundary",
            "constraint_id": "constraint_distilled_instruction_agents_boundary",
            "source_id": "instruction_source_agents_md",
            "snapshot_id": "instruction_snapshot_agents_md",
            "category": "boundary",
            "statement": "Stay inside the repository boundary.",
            "provenance": [
                {
                    "id": "provenance_agents_boundary",
                    "path": "AGENTS.md",
                    "start_line": 3,
                    "end_line": 3,
                }
            ],
        }
    ]
    payload["distillation_warnings"] = [
        "Stale governing distillation excluded: old_policy from instruction_source_agents_md"
    ]

    parsed = CONTRACT_REGISTRY["craik.compiled_prompt"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["distillations"][0]["category"] == "boundary"
    assert dumped["distillation_warnings"] == payload["distillation_warnings"]


def test_task_request_auth_context_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.task_request"])
    payload.update(
        {
            "auth_profile_id": "anthropic:local-cli",
            "operator_subject": "operator-a",
            "operator_issuer": "https://issuer.example.test",
            "source_handoff_id": "handoff_docs_reconcile",
            "source_task_id": "task_docs_reconcile",
            "source_run_id": "run_docs_reconcile",
            "expected_duration_minutes": 90,
        }
    )

    parsed = CONTRACT_REGISTRY["craik.task_request"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["auth_profile_id"] == "anthropic:local-cli"
    assert dumped["operator_subject"] == "operator-a"
    assert dumped["operator_issuer"] == "https://issuer.example.test"
    assert dumped["source_handoff_id"] == "handoff_docs_reconcile"
    assert dumped["source_task_id"] == "task_docs_reconcile"
    assert dumped["source_run_id"] == "run_docs_reconcile"
    assert dumped["expected_duration_minutes"] == 90


def test_instruction_source_snapshot_accepts_oversize_without_hash(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.instruction_source_snapshot"])
    payload.update(
        {
            "id": "instruction_snapshot_agents_md_oversize",
            "content_hash": None,
            "hash_status": "oversize",
            "byte_count": 10485761,
            "line_count": None,
        }
    )

    parsed = CONTRACT_REGISTRY["craik.instruction_source_snapshot"].model_validate(payload)

    assert parsed.hash_status == "oversize"
    assert parsed.content_hash is None


def test_instruction_promotion_review_receipt_hmac_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.instruction_promotion_review"])
    payload["receipt_hmac"] = "a" * 64

    parsed = CONTRACT_REGISTRY["craik.instruction_promotion_review"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["receipt_hmac"] == "a" * 64


def test_agent_message_contract_round_trip() -> None:
    payload = {
        "schema": "craik.agent_message",
        "version": "0.1.0",
        "id": "agent_message_task_docs_agent_a_agent_b_review",
        "task_id": "task_docs_reconcile",
        "kind": "request",
        "status": "sent",
        "from_agent": "agent:a",
        "to_agent": "agent:b",
        "from_role_id": "role_docs_reviewer",
        "from_role_kind": "docs_reviewer",
        "to_role_id": "role_verifier",
        "to_role_kind": "verifier",
        "run_id": "run_docs_reconcile",
        "handoff_id": "handoff_docs_reconcile",
        "subject": "Review docs patch",
        "body": "Please verify the docs patch.",
        "receipt_ids": ["receipt_agent_message_send"],
        "created_at": "2026-05-20T12:00:00Z",
    }

    parsed = CONTRACT_REGISTRY["craik.agent_message"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["schema"] == "craik.agent_message"
    assert dumped["from_role_kind"] == "docs_reviewer"
    assert dumped["receipt_ids"] == ["receipt_agent_message_send"]


def test_agent_message_contract_rejects_oversized_body() -> None:
    payload = {
        "schema": "craik.agent_message",
        "version": "0.1.0",
        "id": "agent_message_task_docs_agent_a_agent_b_review",
        "task_id": "task_docs_reconcile",
        "kind": "request",
        "status": "sent",
        "from_agent": "agent:a",
        "to_agent": "agent:b",
        "subject": "Review docs patch",
        "body": "x" * 32769,
        "receipt_ids": ["receipt_agent_message_send"],
        "created_at": "2026-05-20T12:00:00Z",
    }

    with pytest.raises(ValidationError, match="at most 32768"):
        CONTRACT_REGISTRY["craik.agent_message"].model_validate(payload)


def test_review_contracts_accept_handoff_subject_links(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    request_payload = dict(fixtures["craik.review_request"])
    request_payload["subject_worker_result_ids"] = []
    request_payload["subject_handoff_ids"] = ["handoff_review"]
    result_payload = dict(fixtures["craik.review_result"])
    result_payload["worker_result_ids"] = []
    result_payload["subject_handoff_ids"] = ["handoff_review"]

    request = CONTRACT_REGISTRY["craik.review_request"].model_validate(request_payload)
    result = CONTRACT_REGISTRY["craik.review_result"].model_validate(result_payload)

    assert request.subject_handoff_ids == ["handoff_review"]
    assert result.subject_handoff_ids == ["handoff_review"]


def test_human_delegation_run_id_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.human_delegation_point"])
    payload["run_id"] = "run_docs_reconcile"

    delegation = CONTRACT_REGISTRY["craik.human_delegation_point"].model_validate(payload)

    assert delegation.run_id == "run_docs_reconcile"


def test_scope_change_result_protocol_decision_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.scope_change_result"])
    payload["decision"] = "accepted"
    payload["protocol_decision"] = "sibling"
    payload["sibling_task_id"] = "task_follow_up_scope"
    payload["updated_intent_lock_id"] = None

    result = CONTRACT_REGISTRY["craik.scope_change_result"].model_validate(payload)

    assert result.protocol_decision == "sibling"
    assert result.sibling_task_id == "task_follow_up_scope"


def test_handoff_identity_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.handoff"])
    payload.update(
        {
            "auth_profile_id": "openai:reader",
            "auth_identity_hash": "a" * 64,
            "operator_subject": "operator-a",
            "operator_issuer": "https://issuer.example.test",
        }
    )

    parsed = CONTRACT_REGISTRY["craik.handoff"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["auth_profile_id"] == "openai:reader"
    assert dumped["auth_identity_hash"] == "a" * 64
    assert dumped["operator_subject"] == "operator-a"
    assert dumped["operator_issuer"] == "https://issuer.example.test"


def test_task_run_identity_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.task_run"])
    payload.update(
        {
            "auth_profile_id": "openai:writer",
            "auth_identity_hash": "b" * 64,
            "operator_subject": "operator-b",
            "operator_issuer": "https://issuer.example.test",
            "source_handoff_id": "handoff_docs_reconcile",
            "source_task_id": "task_docs_reconcile",
            "source_run_id": "run_docs_reconcile",
            "role_id": "role_verifier",
            "role_kind": "verifier",
            "completed_step_keys": ["run_docs:1:plan", "run_docs:2:act"],
            "last_step_key": "run_docs:2:act",
            "wall_clock_budget_seconds": 120.5,
            "provider_token_budget": 24000,
            "provider_tokens_used": 1500,
            "provider_token_budget_remaining": 22500,
        }
    )

    parsed = CONTRACT_REGISTRY["craik.task_run"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["auth_profile_id"] == "openai:writer"
    assert dumped["auth_identity_hash"] == "b" * 64
    assert dumped["operator_subject"] == "operator-b"
    assert dumped["source_handoff_id"] == "handoff_docs_reconcile"
    assert dumped["source_task_id"] == "task_docs_reconcile"
    assert dumped["source_run_id"] == "run_docs_reconcile"
    assert dumped["role_id"] == "role_verifier"
    assert dumped["role_kind"] == "verifier"
    assert dumped["operator_issuer"] == "https://issuer.example.test"
    assert dumped["completed_step_keys"] == ["run_docs:1:plan", "run_docs:2:act"]
    assert dumped["last_step_key"] == "run_docs:2:act"
    assert dumped["wall_clock_budget_seconds"] == 120.5
    assert dumped["provider_token_budget"] == 24000
    assert dumped["provider_tokens_used"] == 1500
    assert dumped["provider_token_budget_remaining"] == 22500


def test_tool_result_attestation_hash_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.tool_result_attestation"])
    payload.update(
        {
            "case_file_id": "case_docs_reconcile",
            "output_hash": "b" * 64,
            "hash_algorithm": "sha256",
        }
    )

    parsed = CONTRACT_REGISTRY["craik.tool_result_attestation"].model_validate(payload)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped["case_file_id"] == "case_docs_reconcile"
    assert dumped["output_hash"] == "b" * 64
    assert dumped["hash_algorithm"] == "sha256"


def test_v0_5_integrity_and_resolution_fields_round_trip(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    attestation_payload = dict(fixtures["craik.tool_result_attestation"])
    attestation_payload["receipt_hmac"] = "c" * 64
    recovery_payload = dict(fixtures["craik.recovery_session"])
    recovery_payload.update({"decided_by": "operator-123", "receipt_hmac": "d" * 64})
    debt_payload = dict(fixtures["craik.context_debt_record"])
    debt_payload.update(
        {
            "status": "resolved",
            "resolved_at": "2026-05-16T09:30:00Z",
            "resolved_by_receipt_id": "receipt_context_debt_resolved",
        }
    )
    unknown_payload = dict(fixtures["craik.unknown_record"])
    unknown_payload.update(
        {
            "status": "resolved",
            "resolved_answer": "Use the v0.5 e2e test.",
            "resolved_at": "2026-05-16T09:31:00Z",
            "resolved_by_receipt_id": "receipt_unknown_resolved",
        }
    )
    request_payload = dict(fixtures["craik.context_request"])
    request_payload.update(
        {
            "status": "fulfilled",
            "fulfilled_by": "operator-123",
            "fulfilled_at": "2026-05-16T09:32:00Z",
            "fulfilled_by_receipt_id": "receipt_context_request_fulfilled",
        }
    )

    attestation = CONTRACT_REGISTRY["craik.tool_result_attestation"].model_validate(
        attestation_payload
    )
    recovery = CONTRACT_REGISTRY["craik.recovery_session"].model_validate(recovery_payload)
    debt = CONTRACT_REGISTRY["craik.context_debt_record"].model_validate(debt_payload)
    unknown = CONTRACT_REGISTRY["craik.unknown_record"].model_validate(unknown_payload)
    request = CONTRACT_REGISTRY["craik.context_request"].model_validate(request_payload)

    assert attestation.receipt_hmac == "c" * 64
    assert recovery.decided_by == "operator-123"
    assert recovery.receipt_hmac == "d" * 64
    assert debt.resolved_by_receipt_id == "receipt_context_debt_resolved"
    assert unknown.resolved_by_receipt_id == "receipt_unknown_resolved"
    assert request.fulfilled_by_receipt_id == "receipt_context_request_fulfilled"


def test_v0_5_resolved_runtime_records_require_receipt_linkage(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    debt_payload = dict(fixtures["craik.context_debt_record"])
    debt_payload.update({"status": "resolved", "resolved_at": "2026-05-16T09:30:00Z"})
    unknown_payload = dict(fixtures["craik.unknown_record"])
    unknown_payload.update(
        {
            "status": "resolved",
            "resolved_answer": "Use the v0.5 e2e test.",
            "resolved_at": "2026-05-16T09:31:00Z",
        }
    )
    request_payload = dict(fixtures["craik.context_request"])
    request_payload.update(
        {
            "status": "fulfilled",
            "fulfilled_by": "operator-123",
            "fulfilled_at": "2026-05-16T09:32:00Z",
        }
    )

    with pytest.raises(ValidationError, match="resolved context debt requires"):
        CONTRACT_REGISTRY["craik.context_debt_record"].model_validate(debt_payload)
    with pytest.raises(ValidationError, match="resolved unknowns require"):
        CONTRACT_REGISTRY["craik.unknown_record"].model_validate(unknown_payload)
    with pytest.raises(ValidationError, match="fulfilled context requests require"):
        CONTRACT_REGISTRY["craik.context_request"].model_validate(request_payload)


def test_skill_package_requires_full_semantic_version(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.skill_package"])
    payload["package_version"] = "1.2"

    with pytest.raises(ValidationError, match="semantic-version-like"):
        CONTRACT_REGISTRY["craik.skill_package"].model_validate(payload)


def test_skill_package_requires_expected_input_context_declarations(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.skill_package"])
    payload["context_requirements"] = []

    with pytest.raises(ValidationError, match="require context requirements"):
        CONTRACT_REGISTRY["craik.skill_package"].model_validate(payload)


def test_skill_registry_requires_complete_active_entry_set(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.skill_registry"])
    payload["active_entry_ids"] = ["skill_entry_project_docs"]

    with pytest.raises(ValidationError, match="active skill entries missing"):
        CONTRACT_REGISTRY["craik.skill_registry"].model_validate(payload)


def test_plugin_descriptor_requires_semantic_plugin_version(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.plugin_descriptor"])
    payload["plugin_version"] = "0.6"

    with pytest.raises(ValidationError, match="semantic-version-like"):
        CONTRACT_REGISTRY["craik.plugin_descriptor"].model_validate(payload)


def test_plugin_descriptor_requires_compatibility_boundaries(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.plugin_descriptor"])
    compatibility = dict(payload["compatibility"])
    compatibility["platforms"] = []
    payload["compatibility"] = compatibility

    with pytest.raises(ValidationError, match="platforms"):
        CONTRACT_REGISTRY["craik.plugin_descriptor"].model_validate(payload)


def test_blocked_tool_result_attestation_requires_receipt(
    fixtures: dict[str, dict[str, Any]],
) -> None:
    payload = dict(fixtures["craik.tool_result_attestation"])
    payload.update({"status": "blocked", "receipt_id": None})

    with pytest.raises(ValidationError, match="blocked tool results require receipt_id"):
        CONTRACT_REGISTRY["craik.tool_result_attestation"].model_validate(payload)


def test_runner_contract_models_keep_legacy_import_surface() -> None:
    from craik.contracts import models
    from craik.contracts.runner_models import RunnerMetadata

    assert models.RunnerMetadata is RunnerMetadata


def test_contract_models_keep_split_package_import_surface() -> None:
    from craik.contracts import models
    from craik.contracts.models import core, handoffs, memory

    assert models.TaskRequest is core.TaskRequest
    assert models.MemoryProposal is memory.MemoryProposal
    assert models.TaskRun is handoffs.TaskRun


@pytest.mark.parametrize(
    ("module_name", "export_name", "export_kind"),
    [
        ("craik.contracts.models.core", "TaskRequest", "symbol"),
        ("craik.contracts.models.runtime", "AgentMessage", "symbol"),
        ("craik.contracts.models.handoffs", "Handoff", "symbol"),
        ("craik.contracts.models.instructions", "InstructionSource", "symbol"),
        ("craik.contracts.models.memory", "MemoryProposal", "symbol"),
        ("craik.contracts.models.review", "WorkerFinding", "symbol"),
        ("craik.contracts.models.runtime", "RunOutput", "symbol"),
        ("craik.contracts.models.skills", "SkillPackage", "symbol"),
        ("craik.runtime.memory.memory", "create_proposal", "function"),
        ("craik.runtime.policy.policy", "generate_policy_envelope", "function"),
        ("craik.runtime.runners.runners", "default_runner_capability_matrices", "function"),
    ],
)
def test_compatibility_reexport_modules_define_public_exports(
    module_name: str,
    export_name: str,
    export_kind: str,
) -> None:
    module = importlib.import_module(module_name)

    assert export_name in module.__all__
    exported = getattr(module, export_name)
    assert exported

    if export_kind == "function":
        assert callable(exported)
        if export_name == "create_proposal":
            proposal = exported(
                task_id="task_exports",
                entity="repo:eidetic-labs/craik",
                relation="craik:test",
                value="exported proposal works",
                source="test",
                confidence=1.0,
                scope="local",
                trust_class="observed",
                evidence=[],
            )
            assert proposal.task_id == "task_exports"
        if export_name == "generate_policy_envelope":
            policy = exported(task_id="task_exports", actor="agent:test")
            assert policy.task_id == "task_exports"
        if export_name == "default_runner_capability_matrices":
            matrices = exported()
            assert "codex" in matrices


@pytest.mark.parametrize("name", sorted(CONTRACT_REGISTRY))
def test_wrong_schema_name_is_rejected(
    fixtures: dict[str, dict[str, Any]],
    name: str,
) -> None:
    payload = dict(fixtures[name])
    payload["schema"] = "craik.wrong_schema"

    with pytest.raises(ValidationError):
        CONTRACT_REGISTRY[name].model_validate(payload)


@pytest.mark.parametrize("name", sorted(CONTRACT_REGISTRY))
def test_wrong_schema_version_is_rejected(
    fixtures: dict[str, dict[str, Any]],
    name: str,
) -> None:
    payload = dict(fixtures[name])
    payload["version"] = "9.9.9"

    with pytest.raises(ValidationError):
        CONTRACT_REGISTRY[name].model_validate(payload)


@pytest.mark.parametrize("name", sorted(CONTRACT_REGISTRY))
def test_extra_fields_are_rejected(
    fixtures: dict[str, dict[str, Any]],
    name: str,
) -> None:
    payload = dict(fixtures[name])
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        CONTRACT_REGISTRY[name].model_validate(payload)
