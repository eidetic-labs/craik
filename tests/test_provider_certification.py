import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from craik.runtime.providers.provider_certification import (
    MVP_PROVIDER_REQUIREMENTS,
    ProviderCertification,
    provider_certification_decision,
    provider_certification_matrix,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "providers" / "certification_expectations.json"
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


def test_provider_certification_matrix_matches_fixture_expectations() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    matrix = provider_certification_matrix()
    rows = {row.provider_id: row for row in matrix.rows}

    assert set(fixture["required_provider_ids"]).issubset(rows)
    for provider_id in ("provider_openai", "provider_anthropic", "provider_gemini"):
        row = rows[provider_id]
        assert row.certification_status == "certified"
        assert row.trust_boundary == "third-party"
        for capability, expected in fixture["hosted_capabilities"].items():
            assert getattr(row, capability) == expected
        assert row.live_behavior == "live_opt_in"
        assert "docker" in row.sandbox_compatibility
    fixture_row = rows[fixture["fixture_provider"]["provider_id"]]
    assert fixture_row.certification_status == fixture["fixture_provider"][
        "certification_status"
    ]
    assert fixture_row.live_behavior == fixture["fixture_provider"]["live_behavior"]
    assert fixture_row.sandbox_compatibility == fixture["fixture_provider"][
        "sandbox_compatibility"
    ]
    for provider_id in (
        "provider_local_openai_compatible",
        "provider_local_ollama",
        "provider_local_lm_studio",
        "provider_local_vllm",
    ):
        row = rows[provider_id]
        assert row.certification_status == fixture["local_provider"]["certification_status"]
        assert row.trust_boundary == fixture["local_provider"]["trust_boundary"]
        assert row.live_behavior == fixture["local_provider"]["live_behavior"]
        assert row.sandbox_compatibility == fixture["local_provider"][
            "sandbox_compatibility"
        ]


def test_provider_certification_matrix_marks_unsupported_and_fixture_behavior() -> None:
    rows = {row.provider_id: row for row in provider_certification_matrix().rows}

    assert rows["provider_fixture_local"].models == "unsupported"
    assert rows["provider_fixture_local"].auth == "fixture_only"
    assert rows["provider_local_ollama"].streaming == "unsupported"
    assert rows["provider_local_openai_compatible"].streaming == "supported"


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
