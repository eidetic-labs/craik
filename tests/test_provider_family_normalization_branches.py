"""Task 3.2d-1: legacy ``gemini`` family branches behave like canonical ``google``.

These tests assert the non-mutating normalization sweep: every provider-family
input boundary accepts both the legacy ``gemini`` token and the canonical
``google`` token identically, display-name maps resolve both keys, and the
Google API-key env var is canonically ``CRAIK_GOOGLE_API_KEY`` with
``CRAIK_GEMINI_API_KEY`` retained as a fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from craik.cli_auth_login import _default_env_var
from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.status_metadata import billing_surface_for_profile
from craik.runtime.modeling.settings import _legacy_display_name, readable_model_name
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.providers.provider_runtime import (
    _resolve_secret_ref_name,
    adapter_for_provider,
)
from craik.runtime.shell.textual.support import _display_model_label

# --- profile OAuth validation parity -------------------------------------


def _adc_oauth_profile(provider_family: str) -> AuthProfile:
    return AuthProfile(
        id=f"{provider_family}:vertex",
        kind=CredentialKind.OAUTH,
        provider_family=provider_family,
        oauth_scope_list=["https://www.googleapis.com/auth/cloud-platform"],
        metadata={
            "credential_source": "adc",
            "gcp_project_id": "demo-project",
        },
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("provider_family", ["google", "gemini"])
def test_adc_oauth_profile_validates_for_both_tokens(provider_family: str) -> None:
    """Both the legacy and canonical family tokens validate the ADC OAuth path."""
    profile = _adc_oauth_profile(provider_family)
    assert profile.provider_family == provider_family


@pytest.mark.parametrize("provider_family", ["google", "gemini"])
def test_oauth_profile_missing_gcp_project_id_reports_google(provider_family: str) -> None:
    """The OAuth validation error references the canonical ``google`` token."""
    with pytest.raises(ValueError, match="google oauth auth profiles require"):
        AuthProfile(
            id=f"{provider_family}:vertex",
            kind=CredentialKind.OAUTH,
            provider_family=provider_family,
            oauth_scope_list=["https://www.googleapis.com/auth/cloud-platform"],
            metadata={"credential_source": "adc"},
            created_at=datetime.now(UTC),
        )


@pytest.mark.parametrize("provider_family", ["google", "gemini"])
def test_service_account_oauth_profile_requires_path_for_both_tokens(
    provider_family: str,
) -> None:
    """Service-account OAuth validation fires for both tokens, naming ``google``."""
    with pytest.raises(ValueError, match="google service-account oauth profiles require"):
        AuthProfile(
            id=f"{provider_family}:vertex",
            kind=CredentialKind.OAUTH,
            provider_family=provider_family,
            oauth_scope_list=["https://www.googleapis.com/auth/cloud-platform"],
            metadata={
                "credential_source": "service_account",
                "gcp_project_id": "demo-project",
            },
            created_at=datetime.now(UTC),
        )


# --- status_metadata billing surface parity ------------------------------


@pytest.mark.parametrize("provider_family", ["google", "gemini"])
def test_billing_surface_vertex_for_both_tokens(provider_family: str) -> None:
    profile = _adc_oauth_profile(provider_family)
    assert billing_surface_for_profile(profile, env=None) == "GCP project (Vertex AI)"


@pytest.mark.parametrize("provider_family", ["google", "gemini"])
@pytest.mark.parametrize(
    "env_var",
    ["GEMINI_API_KEY", "GOOGLE_API_KEY", "CRAIK_GEMINI_API_KEY", "CRAIK_GOOGLE_API_KEY"],
)
def test_billing_surface_ai_studio_recognizes_canonical_env_var(
    provider_family: str, env_var: str
) -> None:
    profile = AuthProfile(
        id=f"{provider_family}:default",
        kind=CredentialKind.API_KEY,
        provider_family=provider_family,
        metadata={"env_var": env_var},
        created_at=datetime.now(UTC),
    )
    assert billing_surface_for_profile(profile, env=None) == "Google AI Studio (per-token)"


# --- display-name maps ----------------------------------------------------


@pytest.mark.parametrize("provider_family", ["google", "gemini"])
def test_legacy_display_name_resolves_both_tokens(provider_family: str) -> None:
    label = _legacy_display_name(provider_family, "gemini-2.5-pro", {})
    assert label.startswith("Google Gemini ")


@pytest.mark.parametrize("provider_family", ["google", "gemini"])
def test_readable_model_name_resolves_both_tokens(provider_family: str) -> None:
    # role-2 model NAME parsing is preserved regardless of the family token.
    assert readable_model_name(provider_family, "gemini-2.5-pro") == "Gemini 2.5 Pro"


@pytest.mark.parametrize("provider", ["google", "gemini"])
def test_display_model_label_resolves_both_tokens(provider: str) -> None:
    assert _display_model_label(f"{provider}/gemini-2.5-pro") == "Google Gemini 2.5 Pro"


# --- env-var dual-read ----------------------------------------------------


def test_default_env_var_for_google_is_canonical() -> None:
    """The google family's canonical login env var is ``CRAIK_GOOGLE_API_KEY``."""
    assert _default_env_var("google") == "CRAIK_GOOGLE_API_KEY"
    # The legacy alias normalizes to the same canonical env var.
    assert _default_env_var("gemini") == "CRAIK_GOOGLE_API_KEY"


def test_registry_secret_ref_names_canonical_first_with_legacy_fallback() -> None:
    registry = default_model_provider_registry()
    provider = registry.require("provider_gemini")
    assert provider.secret_ref_names == ["CRAIK_GOOGLE_API_KEY", "CRAIK_GEMINI_API_KEY"]


def test_secret_ref_resolution_prefers_canonical_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_GOOGLE_API_KEY", "canonical")
    monkeypatch.setenv("CRAIK_GEMINI_API_KEY", "legacy")
    chosen = _resolve_secret_ref_name(["CRAIK_GOOGLE_API_KEY", "CRAIK_GEMINI_API_KEY"])
    assert chosen == "CRAIK_GOOGLE_API_KEY"


def test_secret_ref_resolution_falls_back_to_legacy_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CRAIK_GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("CRAIK_GEMINI_API_KEY", "legacy")
    chosen = _resolve_secret_ref_name(["CRAIK_GOOGLE_API_KEY", "CRAIK_GEMINI_API_KEY"])
    assert chosen == "CRAIK_GEMINI_API_KEY"


def test_secret_ref_resolution_defaults_to_canonical_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CRAIK_GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("CRAIK_GEMINI_API_KEY", raising=False)
    chosen = _resolve_secret_ref_name(["CRAIK_GOOGLE_API_KEY", "CRAIK_GEMINI_API_KEY"])
    assert chosen == "CRAIK_GOOGLE_API_KEY"


def test_adapter_for_google_provider_reads_legacy_env_var_when_only_legacy_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CRAIK_GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("CRAIK_GEMINI_API_KEY", "legacy")
    registry = default_model_provider_registry()
    adapter = adapter_for_provider(registry.require("provider_gemini"))
    assert adapter.config.secret_ref_name == "CRAIK_GEMINI_API_KEY"


def test_adapter_for_google_provider_prefers_canonical_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_GOOGLE_API_KEY", "canonical")
    monkeypatch.setenv("CRAIK_GEMINI_API_KEY", "legacy")
    registry = default_model_provider_registry()
    adapter = adapter_for_provider(registry.require("provider_gemini"))
    assert adapter.config.secret_ref_name == "CRAIK_GOOGLE_API_KEY"
