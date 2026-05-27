"""Redacted auth status metadata helpers."""

from __future__ import annotations

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources.anthropic_env import resolve_anthropic_credential_from_env


def credential_source_for_profile(
    profile: AuthProfile,
    env: dict[str, str] | None,
) -> str | None:
    """Return the redacted credential source label shown in auth status."""
    if profile.provider_family != "anthropic" or profile.kind is not CredentialKind.API_KEY:
        return None
    env_var = profile.metadata.get("env_var")
    if not isinstance(env_var, str):
        return None
    credential = resolve_anthropic_credential_from_env(
        env,
        fallback_env_vars=(
            "ANTHROPIC_TOKEN",
            env_var,
            "ANTHROPIC_API_KEY",
            "CRAIK_ANTHROPIC_API_KEY",
        ),
    )
    return credential.display if credential is not None else None


def billing_surface_for_profile(
    profile: AuthProfile,
    env: dict[str, str] | None,
) -> str | None:
    """Return the operator-facing billing route for a provider profile."""
    if profile.provider_family == "anthropic":
        return _anthropic_billing_surface(profile, env)
    if profile.provider_family == "openai":
        return _openai_billing_surface(profile)
    if profile.provider_family == "gemini":
        return _gemini_billing_surface(profile)
    return None


def _anthropic_billing_surface(
    profile: AuthProfile,
    env: dict[str, str] | None,
) -> str | None:
    if profile.kind is CredentialKind.API_KEY:
        env_var = profile.metadata.get("env_var")
        if not isinstance(env_var, str):
            return None
        credential = resolve_anthropic_credential_from_env(
            env,
            fallback_env_vars=(
                "ANTHROPIC_TOKEN",
                env_var,
                "ANTHROPIC_API_KEY",
                "CRAIK_ANTHROPIC_API_KEY",
            ),
        )
        if credential is None:
            return None
        if credential.source == "env:CLAUDE_CODE_OAUTH_TOKEN":
            return "Claude Pro/Max subscription"
        if credential.source == "env:ANTHROPIC_TOKEN":
            return "operator-supplied token"
        if credential.source in {"env:ANTHROPIC_API_KEY", "env:CRAIK_ANTHROPIC_API_KEY"}:
            return "Anthropic Console API (per-token)"
        return "unknown"
    if profile.kind is CredentialKind.KEYRING_REF:
        if profile.metadata.get("credential_mode") == "claude-cli":
            return "Claude CLI subscription / extra usage"
        if profile.metadata.get("credential_mode") == "agent-sdk":
            return "Claude Agent SDK subscription / extra usage"
        return "Anthropic Console API (per-token)"
    if (
        profile.kind is CredentialKind.MARKER
        and profile.metadata.get("external_runtime") == "claude-cli"
    ):
        return "Claude CLI subscription"
    if profile.kind is CredentialKind.OAUTH:
        return "Claude subscription"
    return None


def _openai_billing_surface(profile: AuthProfile) -> str | None:
    if profile.kind is CredentialKind.OAUTH:
        return "OpenAI subscription"
    if profile.kind in {
        CredentialKind.API_KEY,
        CredentialKind.KEYRING_REF,
        CredentialKind.SECRET_REF,
    }:
        return "OpenAI Platform API (per-token)"
    return None


def _gemini_billing_surface(profile: AuthProfile) -> str | None:
    if profile.kind is CredentialKind.OAUTH:
        source = profile.metadata.get("credential_source")
        if source == "adc":
            return "GCP project (Vertex AI)"
        if source == "service_account":
            return "GCP project (Vertex AI, service-account)"
    if profile.kind is CredentialKind.API_KEY:
        env_var = profile.metadata.get("env_var")
        if env_var in {"GEMINI_API_KEY", "GOOGLE_API_KEY", "CRAIK_GEMINI_API_KEY"}:
            return "Google AI Studio (per-token)"
    return None
