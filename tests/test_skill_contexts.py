import pytest
from pydantic import ValidationError

from craik.contracts.models import SkillInvocationContext, SkillPackage
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _context(**overrides: object) -> SkillInvocationContext:
    payload = {
        "id": "skill_context_docs_reconcile",
        "task_id": "task_docs_reconcile",
        "skill_package_id": "skill_docs_reconcile",
        "policy_envelope_id": "policy_docs_reconcile",
        "handoff_id": "handoff_docs_reconcile",
        "inputs": [
            {
                "schema_name": "craik.case_file",
                "contract_id": "case_docs_reconcile",
                "required": True,
                "trust_boundary": "project",
                "summary": "Task case file supplied to the skill.",
                "evidence_ids": ["evidence_readme_status"],
            }
        ],
        "outputs": [
            {
                "schema_name": "craik.worker_result",
                "contract_id": "worker_result_docs_reconcile_verifier",
                "required": True,
                "produced": True,
                "summary": "Worker result produced by the skill.",
                "evidence_ids": ["evidence_worker_result_docs_reconcile"],
            }
        ],
        "omissions": [],
        "evidence_ids": ["evidence_readme_status"],
        "receipt_ids": ["receipt_runner_fixture"],
        "redacted": True,
        "created_at": "2026-05-16T15:50:00Z",
    }
    payload.update(overrides)
    return SkillInvocationContext.model_validate(payload)


def _package(**overrides: object) -> SkillPackage:
    payload = {
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
                "expected_input_schemas": ["craik.case_file"],
                "expected_output_schemas": ["craik.worker_result"],
            }
        ],
        "docs": ["SKILL.md"],
        "expected_input_schemas": ["craik.case_file"],
        "expected_output_schemas": ["craik.worker_result"],
        "context_requirements": [
            {
                "schema_name": "craik.case_file",
                "required": True,
                "trust_boundary": "project",
                "missing_context_behavior": "reject",
                "summary": "Task case file required before invoking the skill.",
            }
        ],
        "created_at": "2026-05-16T15:30:00Z",
    }
    payload.update(overrides)
    return SkillPackage.model_validate(payload)


def test_skill_invocation_context_round_trips_in_store(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        context = _context()
        store.put_skill_invocation_context(context)

        assert store.get_skill_invocation_context(context.id) == context
        assert store.list_skill_invocation_contexts() == [context]
        assert context.redacted is True
    finally:
        store.close()


def test_skill_invocation_context_requires_inputs() -> None:
    with pytest.raises(ValidationError):
        _context(inputs=[])


def test_skill_invocation_context_requires_outputs_or_omissions() -> None:
    with pytest.raises(ValidationError, match="outputs or omissions"):
        _context(outputs=[], omissions=[])


def test_skill_invocation_context_tracks_omissions() -> None:
    context = _context(
        outputs=[
            {
                "schema_name": "craik.worker_result",
                "required": True,
                "produced": False,
                "summary": "Worker result was expected but not produced.",
            }
        ],
        omissions=[
            {
                "schema_name": "craik.worker_result",
                "reason": "The skill stopped before emitting structured output.",
                "impact": "A verifier needs to rerun or replace the skill output.",
                "severity": "high",
                "mitigation": "Create a context request before retrying.",
                "evidence_ids": ["evidence_readme_status"],
            }
        ],
    )

    assert context.omissions[0].schema_name == "craik.worker_result"


def test_skill_invocation_context_requires_policy_links_and_redaction() -> None:
    with pytest.raises(ValidationError, match="policy_envelope_id"):
        _context(policy_envelope_id="")

    with pytest.raises(ValidationError, match="must be redacted"):
        _context(redacted=False)


def test_skill_package_validates_supplied_invocation_context() -> None:
    package = _package()
    context = _context()

    package.validate_invocation_context(context)


def test_skill_package_rejects_missing_required_context() -> None:
    package = _package()
    context = _context(
        inputs=[
            {
                "schema_name": "craik.other_context",
                "contract_id": "other_context",
                "required": True,
                "trust_boundary": "project",
                "summary": "Wrong context supplied.",
            }
        ]
    )

    with pytest.raises(ValueError, match="missing required skill context input"):
        package.validate_invocation_context(context)


def test_skill_package_rejects_context_from_wrong_trust_boundary() -> None:
    package = _package()
    context = _context(
        inputs=[
            {
                "schema_name": "craik.case_file",
                "contract_id": "case_docs_reconcile",
                "required": True,
                "trust_boundary": "external",
                "summary": "Case file supplied across the wrong boundary.",
            }
        ]
    )

    with pytest.raises(ValueError, match="trust_boundary does not match"):
        package.validate_invocation_context(context)


def test_skill_package_can_require_omission_for_missing_context() -> None:
    package = _package(
        context_requirements=[
            {
                "schema_name": "craik.case_file",
                "required": True,
                "trust_boundary": "project",
                "missing_context_behavior": "record_omission",
                "summary": "Task case file should be supplied or omitted explicitly.",
            }
        ]
    )
    context = _context(
        inputs=[
            {
                "schema_name": "craik.other_context",
                "contract_id": "other_context",
                "required": True,
                "trust_boundary": "project",
                "summary": "Alternative context supplied.",
            }
        ],
        omissions=[
            {
                "schema_name": "craik.case_file",
                "reason": "Case file was unavailable.",
                "impact": "Skill can only produce a partial result.",
                "severity": "medium",
                "mitigation": "Create a context request before a complete rerun.",
            }
        ],
    )

    package.validate_invocation_context(context)


def test_skill_package_can_degrade_when_context_is_missing() -> None:
    package = _package(
        context_requirements=[
            {
                "schema_name": "craik.case_file",
                "required": True,
                "trust_boundary": "project",
                "missing_context_behavior": "degrade",
                "summary": "Task case file enables a complete result.",
            }
        ]
    )
    context = _context(
        inputs=[
            {
                "schema_name": "craik.other_context",
                "contract_id": "other_context",
                "required": True,
                "trust_boundary": "project",
                "summary": "Alternative context supplied.",
            }
        ],
    )

    package.validate_invocation_context(context)
