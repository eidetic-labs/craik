"""Tests for the read-only `VendorProfile` metadata facade."""

from __future__ import annotations

import pytest

from craik.runtime.auth.sources.anthropic_oauth import (
    ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT,
    ANTHROPIC_OAUTH_SCOPES,
)
from craik.runtime.auth.sources.google_oauth import GEMINI_OAUTH_SCOPES
from craik.runtime.auth.sources.openai_oauth import OPENAI_OAUTH_SCOPES
from craik.runtime.backend.adapters.vendor_profile import (
    VendorProfile,
    vendor_profile,
)
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.providers.provider_transport import ProviderTransportError


def test_vendor_profile_anthropic_composes_registry_and_auth_metadata() -> None:
    profile = vendor_profile("anthropic")

    assert isinstance(profile, VendorProfile)
    assert profile.vendor == "anthropic"
    # identity sourced from the registry provider entry, not re-declared.
    assert profile.identity.provider_id == "provider_anthropic"
    assert profile.identity.display_name == "Anthropic Claude Provider"
    assert profile.identity.provider_family == "anthropic"
    # model catalog composed from the registry provider metadata.
    assert profile.model_catalog
    assert profile.model_catalog.default_model == "claude-sonnet-4-20250514"
    # auth metadata sourced from the per-vendor OAuth source constants.
    assert profile.auth_metadata.authorization_endpoint == (ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT)
    assert profile.auth_metadata.scopes == tuple(ANTHROPIC_OAUTH_SCOPES)
    assert profile.auth_metadata.profile_namespace == "anthropic:subscription"


def test_vendor_profile_openai_composes_registry_and_auth_metadata() -> None:
    profile = vendor_profile("openai")

    assert profile.vendor == "openai"
    assert profile.identity.provider_id == "provider_openai"
    assert profile.model_catalog.default_model == "gpt-5.2"
    assert profile.auth_metadata.scopes == tuple(OPENAI_OAUTH_SCOPES)
    assert profile.auth_metadata.profile_namespace == "openai:subscription"


def test_vendor_profile_google_composes_registry_and_auth_metadata() -> None:
    profile = vendor_profile("google")

    assert profile.vendor == "google"
    assert profile.identity.provider_id == "provider_google"
    # role-2: google registry default model stays the literal "gemini-2.5-pro".
    assert profile.model_catalog.default_model == "gemini-2.5-pro"
    assert profile.auth_metadata.scopes == tuple(GEMINI_OAUTH_SCOPES)
    assert profile.auth_metadata.profile_namespace == "google:vertex"


def test_vendor_profile_gemini_alias_resolves_to_google_profile() -> None:
    legacy = vendor_profile("gemini")
    canonical = vendor_profile("google")

    assert legacy.vendor == "google"
    assert legacy == canonical


def test_vendor_profile_unknown_vendor_raises_value_error() -> None:
    with pytest.raises(ValueError):
        vendor_profile("not-a-vendor")


def test_model_catalog_is_composed_from_registry_not_duplicated() -> None:
    # Prove composition: the catalog reflects the registry's resolved default
    # model rather than a profile-local hardcoded list.
    registry = default_model_provider_registry()
    expected = registry.require("provider_google").metadata["default_model"]

    profile = vendor_profile("google")

    assert profile.model_catalog.default_model == expected == "gemini-2.5-pro"
    assert expected in profile.model_catalog.models


def test_normalize_model_name_strips_vendor_prefix_and_keeps_claude_id() -> None:
    profile = vendor_profile("anthropic")

    assert (
        profile.normalize_model_name("anthropic/claude-sonnet-4-20250514")
        == "claude-sonnet-4-20250514"
    )
    assert profile.normalize_model_name("claude-sonnet-4-20250514") == "claude-sonnet-4-20250514"


def test_classify_error_maps_auth_failure_to_auth_category() -> None:
    profile = vendor_profile("anthropic")

    auth_error = ProviderTransportError("unauthorized", status_code=401)
    rate_error = ProviderTransportError("slow down", status_code=429)
    bad_request = ProviderTransportError("bad", status_code=400)
    transient = ProviderTransportError("server", status_code=503)

    assert profile.classify_error(auth_error) == "auth"
    assert profile.classify_error(rate_error) == "rate_limit"
    assert profile.classify_error(bad_request) == "invalid_request"
    assert profile.classify_error(transient) == "transient"
    assert profile.classify_error(ValueError("???")) == "unknown"
