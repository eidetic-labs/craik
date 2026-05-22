import pytest
from pydantic import ValidationError

from craik.runtime.providers.provider_certification import (
    MVP_PROVIDER_REQUIREMENTS,
    ProviderCertification,
    provider_certification_decision,
)


def test_openai_provider_certification_requires_all_mvp_capabilities() -> None:
    certification = _certification(provider_family="openai", provider_id="provider_openai")

    decision = provider_certification_decision(certification)

    assert decision.status == "certified"
    assert decision.provider_family == "openai"
    assert decision.missing_requirements == []
    assert decision.blocked_requirements == []
    assert decision.required_controls == [
        "policy_envelope",
        "evidence",
        "receipts",
        "redaction",
        "secret_references",
    ]


def test_anthropic_provider_certification_uses_same_mvp_bar() -> None:
    certification = _certification(provider_family="anthropic", provider_id="provider_anthropic")

    decision = provider_certification_decision(certification)

    assert decision.status == "certified"
    assert decision.provider_family == "anthropic"
    assert decision.missing_requirements == []


def test_gemini_provider_certification_uses_same_mvp_bar() -> None:
    certification = _certification(provider_family="gemini", provider_id="provider_gemini")

    decision = provider_certification_decision(certification)

    assert decision.status == "certified"
    assert decision.provider_family == "gemini"
    assert decision.missing_requirements == []


def test_provider_certification_blocks_missing_or_blocked_requirements() -> None:
    certification = _certification(
        supported_requirements=["chat", "streaming", "redaction", "receipts"],
        blocked_requirements=["tool_calls"],
    )

    decision = provider_certification_decision(certification)

    assert decision.status == "blocked"
    assert "structured_output" in decision.missing_requirements
    assert decision.blocked_requirements == ["tool_calls"]


def test_provider_certification_validates_known_requirement_names() -> None:
    with pytest.raises(ValidationError, match="unknown provider certification requirements"):
        _certification(supported_requirements=[*MVP_PROVIDER_REQUIREMENTS, "ambient_authority"])


def test_provider_certification_requires_policy_evidence_receipts_and_docs() -> None:
    with pytest.raises(ValidationError, match="policy_envelope_id"):
        _certification(policy_envelope_id="")

    with pytest.raises(ValidationError):
        _certification(evidence_ids=[])

    with pytest.raises(ValidationError):
        _certification(receipt_ids=[])

    with pytest.raises(ValidationError, match="docs_ref"):
        _certification(docs_ref="")


def _certification(**overrides: object) -> ProviderCertification:
    payload = {
        "id": "provider_certification_openai",
        "provider_id": "provider_openai",
        "provider_family": "openai",
        "model_refs": ["mvp_primary_model"],
        "supported_requirements": list(MVP_PROVIDER_REQUIREMENTS),
        "blocked_requirements": [],
        "policy_envelope_id": "policy_provider_certification",
        "evidence_ids": ["evidence_provider_docs"],
        "receipt_ids": ["receipt_provider_certification"],
        "docs_ref": "docs/reference/provider-certification.md",
    }
    payload.update(overrides)
    return ProviderCertification.model_validate(payload)
