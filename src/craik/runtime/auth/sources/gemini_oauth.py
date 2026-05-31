"""Deprecated import path. Use craik.runtime.auth.sources.google_oauth.

Retained for back-compat during the gemini→google rename.
"""

from __future__ import annotations

from craik.runtime.auth.sources.google_oauth import (  # noqa: F401
    GEMINI_ADC_CREDENTIAL_SOURCE,
    GEMINI_OAUTH_BILLING_SURFACE,
    GEMINI_OAUTH_SCOPES,
    GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE,
    GeminiCredentialResult,
    GeminiOAuthError,
    GoogleOAuthError,
    headers_for_credentials,
    headers_for_profile,
    resolve_via_adc,
    resolve_via_service_account,
    store_gemini_adc_profile,
    store_gemini_service_account_profile,
    store_google_adc_profile,
    store_google_service_account_profile,
)

__all__ = [
    "GEMINI_ADC_CREDENTIAL_SOURCE",
    "GEMINI_OAUTH_BILLING_SURFACE",
    "GEMINI_OAUTH_SCOPES",
    "GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE",
    "GeminiCredentialResult",
    "GeminiOAuthError",
    "GoogleOAuthError",
    "headers_for_credentials",
    "headers_for_profile",
    "resolve_via_adc",
    "resolve_via_service_account",
    "store_gemini_adc_profile",
    "store_gemini_service_account_profile",
    "store_google_adc_profile",
    "store_google_service_account_profile",
]
