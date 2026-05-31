"""Provider certification contracts for MVP model support."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel, ModelProvider
from craik.runtime.providers.model_providers import (
    ModelProviderRegistry,
    default_model_provider_registry,
)
from craik.runtime.providers.provider_transport import normalize_provider_family

MVPProviderFamily = Literal["openai", "anthropic", "google", "gemini"]
ProviderCertificationStatus = Literal["certified", "blocked"]
ProviderMatrixFamily = Literal[
    "openai", "anthropic", "google", "gemini", "chat_completions", "fixture"
]
ProviderMatrixStatus = Literal["certified", "fixture_only", "unsupported"]
ProviderCapabilityStatus = Literal["supported", "fixture_only", "unsupported"]

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
                "provider requirements cannot be both supported and blocked: " f"{sorted(overlap)}"
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


class ProviderCertificationMatrixRow(CraikModel):
    """Machine-checkable capability row for one registered provider."""

    provider_id: str
    provider_family: ProviderMatrixFamily
    certification_status: ProviderMatrixStatus
    trust_boundary: str
    auth: ProviderCapabilityStatus
    models: ProviderCapabilityStatus
    streaming: ProviderCapabilityStatus
    tools: ProviderCapabilityStatus
    structured_output: ProviderCapabilityStatus
    receipts: ProviderCapabilityStatus
    budgets: ProviderCapabilityStatus
    retry_behavior: ProviderCapabilityStatus
    sandbox_compatibility: list[str] = Field(default_factory=list)
    live_behavior: str
    docs_ref: str
    notes: list[str] = Field(default_factory=list)


class ProviderCertificationMatrix(CraikModel):
    """Generated provider certification matrix."""

    schema_: Literal["craik.provider_certification_matrix"] = Field(
        default="craik.provider_certification_matrix",
        alias="schema",
    )
    version: Literal["0.1.0"] = "0.1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rows: list[ProviderCertificationMatrixRow]


def provider_certification_matrix(
    registry: ModelProviderRegistry | None = None,
) -> ProviderCertificationMatrix:
    """Return a stable certification matrix for registered model providers."""
    providers = (registry or default_model_provider_registry()).list()
    return ProviderCertificationMatrix(
        rows=[_provider_matrix_row(provider) for provider in providers],
    )


def provider_certification_matrix_payload(
    registry: ModelProviderRegistry | None = None,
) -> dict[str, object]:
    """Return the provider certification matrix as JSON-ready data."""
    return provider_certification_matrix(registry).model_dump(mode="json", by_alias=True)


def _provider_matrix_row(provider: ModelProvider) -> ProviderCertificationMatrixRow:
    provider_id = provider.id
    family = cast(ProviderMatrixFamily, normalize_provider_family(provider.provider))
    capability_names = {capability.name for capability in provider.capabilities}
    docs = list(provider.docs)
    runtime_path = provider.runtime_path
    trust_boundary = provider.trust_boundary
    has_model = bool(provider.metadata.get("default_model"))
    is_fixture = family == "fixture"
    is_local = provider_id.startswith("provider_local_") or trust_boundary == "local"
    status: ProviderMatrixStatus = "certified"
    if is_fixture:
        status = "fixture_only"
    elif family not in {"openai", "anthropic", "google", "chat_completions"}:
        status = "unsupported"
    notes: list[str] = []
    live_behavior = "live_opt_in"
    if is_fixture:
        live_behavior = "fixture_by_default"
        notes.append("Deterministic fixture provider; not a live model route.")
    elif is_local:
        live_behavior = "operator_local_endpoint_required"
        notes.append("Local endpoint availability is operator-managed.")
    return ProviderCertificationMatrixRow(
        provider_id=provider_id,
        provider_family=family,
        certification_status=status,
        trust_boundary=trust_boundary,
        auth=_auth_status(provider),
        models="supported" if has_model else "unsupported",
        streaming=_capability_status("model.streaming", capability_names, is_fixture),
        tools=_capability_status("model.tool_calls", capability_names, is_fixture),
        structured_output=_capability_status(
            "model.structured_output",
            capability_names,
            is_fixture,
        ),
        receipts="fixture_only" if is_fixture else _runtime_status(runtime_path),
        budgets=_budget_status(provider, is_fixture),
        retry_behavior="fixture_only" if is_fixture else _runtime_status(runtime_path),
        sandbox_compatibility=_sandbox_compatibility(provider_id, trust_boundary, is_fixture),
        live_behavior=live_behavior,
        docs_ref="docs/reference/provider-certification.md"
        if "docs/reference/provider-certification.md" in docs
        else "docs/reference/model-providers.md",
        notes=notes,
    )


def _auth_status(provider: ModelProvider) -> ProviderCapabilityStatus:
    if provider.provider == "fixture":
        return "fixture_only"
    if provider.secret_ref_names:
        return "supported"
    if provider.trust_boundary == "local":
        return "supported"
    return "unsupported"


def _capability_status(
    name: str,
    capability_names: set[str],
    is_fixture: bool,
) -> ProviderCapabilityStatus:
    if name in capability_names:
        return "fixture_only" if is_fixture else "supported"
    return "unsupported"


def _runtime_status(runtime_path: str | None) -> ProviderCapabilityStatus:
    return "supported" if runtime_path else "unsupported"


def _budget_status(provider: ModelProvider, is_fixture: bool) -> ProviderCapabilityStatus:
    if is_fixture:
        return "fixture_only"
    return "supported" if provider.budget_ref and provider.quota_ref else "unsupported"


def _sandbox_compatibility(
    provider_id: str,
    trust_boundary: str,
    is_fixture: bool,
) -> list[str]:
    if is_fixture:
        return ["fixture"]
    if provider_id.startswith("provider_local_") or trust_boundary == "local":
        return ["local_process"]
    return ["local_process", "docker", "remote_shell", "browser_tool"]
