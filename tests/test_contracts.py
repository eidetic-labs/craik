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
