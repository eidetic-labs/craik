"""Provider-family token normalization and back-compat alias resolution."""

from __future__ import annotations

import pytest

from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.providers.provider_certification import _provider_matrix_row
from craik.runtime.providers.provider_config import ProviderRuntimeConfig
from craik.runtime.providers.provider_runtime import adapter_for_provider
from craik.runtime.providers.provider_runtime_google import GoogleProviderAdapter
from craik.runtime.providers.provider_runtime_support import _official_docs_for_family
from craik.runtime.providers.provider_transport import normalize_provider_family


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        ("gemini", "google"),
        ("google", "google"),
        ("openai", "openai"),
        ("anthropic", "anthropic"),
        ("chat_completions", "chat_completions"),
    ],
)
def test_normalize_provider_family_maps_legacy_alias(family: str, expected: str) -> None:
    """The legacy ``gemini`` token normalizes to the canonical ``google`` token."""
    assert normalize_provider_family(family) == expected


def test_registry_google_provider_uses_canonical_token() -> None:
    """The default Google provider entry exposes the canonical ``google`` family token."""
    registry = default_model_provider_registry()
    provider = registry.require("provider_gemini")
    assert provider.provider == "google"
    assert provider.budget_ref == "budget_google_monthly"
    assert provider.quota_ref == "quota_google_daily"
    # role-2 surfaces stay on the real Google product names.
    assert provider.metadata["default_model"] == "gemini-2.5-pro"
    assert provider.metadata["base_url"] == "https://generativelanguage.googleapis.com"


def test_adapter_for_google_provider_accepts_canonical_token() -> None:
    """Building the runtime adapter from the google-canonical entry succeeds."""
    registry = default_model_provider_registry()
    adapter = adapter_for_provider(registry.require("provider_gemini"))
    assert adapter.config.provider_family == "google"


def test_adapter_for_provider_accepts_legacy_gemini_token() -> None:
    """A config arriving with the legacy ``gemini`` family still builds the google adapter."""
    config = ProviderRuntimeConfig(
        provider_id="provider_gemini",
        provider_family="gemini",
        model="gemini-2.5-pro",
        secret_ref_name="CRAIK_GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com",
        docs_refs=_official_docs_for_family("gemini"),
    )
    # The legacy token is accepted as an alias; the adapter constructs.
    adapter = GoogleProviderAdapter(config)
    assert adapter is not None


def test_matrix_row_normalizes_legacy_gemini_family() -> None:
    """A provider carrying the legacy ``gemini`` token classifies as ``google`` would."""
    registry = default_model_provider_registry()
    google_provider = registry.require("provider_gemini")
    assert google_provider.provider == "google"

    google_row = _provider_matrix_row(google_provider)
    # Simulate a provider that still carries the legacy family token.
    legacy_provider = google_provider.model_copy(update={"provider": "gemini"})
    legacy_row = _provider_matrix_row(legacy_provider)

    # The legacy token must not be mis-classified as unsupported.
    assert legacy_row.certification_status != "unsupported"
    assert legacy_row.certification_status == google_row.certification_status
    # The matrix column shows the canonical google token, not the legacy alias.
    assert legacy_row.provider_family == "google"
    assert google_row.provider_family == "google"
