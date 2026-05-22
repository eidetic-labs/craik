"""Provider certification contracts for MVP model support."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel

MVPProviderFamily = Literal["openai", "anthropic", "gemini"]
ProviderCertificationStatus = Literal["certified", "blocked"]

MVP_PROVIDER_REQUIREMENTS = (
    "chat",
    "streaming",
    "tool_calls",
    "structured_output",
    "usage_metadata",
    "retryable_errors",
    "redaction",
    "receipts",
)


class ProviderCertification(CraikModel):
    """Certification record for an MVP model provider path."""

    id: str
    provider_id: str
    provider_family: MVPProviderFamily
    model_refs: list[str] = Field(min_length=1)
    supported_requirements: list[str] = Field(default_factory=list)
    blocked_requirements: list[str] = Field(default_factory=list)
    policy_envelope_id: str
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(min_length=1)
    docs_ref: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_certification(self) -> ProviderCertification:
        """Keep certifications complete and auditable."""
        if not self.policy_envelope_id:
            raise ValueError("provider certification requires policy_envelope_id")
        if not self.docs_ref:
            raise ValueError("provider certification requires docs_ref")
        unknown = set(self.supported_requirements) | set(self.blocked_requirements)
        unknown -= set(MVP_PROVIDER_REQUIREMENTS)
        if unknown:
            raise ValueError(f"unknown provider certification requirements: {sorted(unknown)}")
        overlap = set(self.supported_requirements) & set(self.blocked_requirements)
        if overlap:
            raise ValueError(
                "provider requirements cannot be both supported and blocked: "
                f"{sorted(overlap)}"
            )
        return self


class ProviderCertificationDecision(CraikModel):
    """Decision summarizing whether a provider is MVP-ready."""

    status: ProviderCertificationStatus
    provider_id: str
    provider_family: MVPProviderFamily
    missing_requirements: list[str] = Field(default_factory=list)
    blocked_requirements: list[str] = Field(default_factory=list)
    required_controls: list[str] = Field(default_factory=list)


def provider_certification_decision(
    certification: ProviderCertification,
) -> ProviderCertificationDecision:
    """Return whether a provider certification satisfies the MVP bar."""
    missing = [
        requirement
        for requirement in MVP_PROVIDER_REQUIREMENTS
        if requirement not in certification.supported_requirements
    ]
    blocked = list(certification.blocked_requirements)
    status: ProviderCertificationStatus = "certified"
    if missing or blocked:
        status = "blocked"
    return ProviderCertificationDecision(
        status=status,
        provider_id=certification.provider_id,
        provider_family=certification.provider_family,
        missing_requirements=missing,
        blocked_requirements=blocked,
        required_controls=[
            "policy_envelope",
            "evidence",
            "receipts",
            "redaction",
            "secret_references",
        ],
    )
