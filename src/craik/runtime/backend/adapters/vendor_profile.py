"""Read-only ``VendorProfile`` metadata facade over the provider registry.

A :class:`VendorProfile` is a thin, read-only composition object. It does NOT
re-declare provider data: identity and model catalog are read from the default
:class:`~craik.runtime.providers.model_providers.ModelProviderRegistry`, and the
OAuth ``auth_metadata`` is sourced from the per-vendor OAuth sources under
``craik.runtime.auth.sources``.

Per design §4.4 ownership table the profile owns METADATA only. It performs no
credential acquisition, no provider invocation, and no network access.
"""

from __future__ import annotations

from dataclasses import dataclass

from craik.runtime.auth.sources.anthropic_oauth import (
    ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT,
    ANTHROPIC_OAUTH_SCOPES,
    ANTHROPIC_OAUTH_TOKEN_ENDPOINT,
)
from craik.runtime.auth.sources.google_oauth import GEMINI_OAUTH_SCOPES
from craik.runtime.auth.sources.openai_oauth import (
    OPENAI_OAUTH_AUTHORIZATION_ENDPOINT,
    OPENAI_OAUTH_SCOPES,
    OPENAI_OAUTH_TOKEN_ENDPOINT,
)
from craik.runtime.providers.model_providers import (
    ModelProviderRegistry,
    default_model_provider_registry,
)
from craik.runtime.providers.provider_transport import (
    ProviderTransportError,
    normalize_provider_family,
)

# Canonical vendor token -> registry provider id. Mirrors the family->provider-id
# mapping already used in modeling/settings.py and backend/session.py; the legacy
# "gemini" token is normalized to "google" before lookup.
_VENDOR_PROVIDER_IDS = {
    "anthropic": "provider_anthropic",
    "openai": "provider_openai",
    "google": "provider_google",
}

# Stable error category set returned by ``VendorProfile.classify_error``.
ErrorCategory = str


@dataclass(frozen=True)
class VendorIdentity:
    """Vendor identity sourced from the registry provider entry."""

    provider_id: str
    display_name: str
    provider_family: str


@dataclass(frozen=True)
class VendorModelCatalog:
    """Vendor model catalog composed from registry provider metadata."""

    default_model: str
    models: tuple[str, ...]


@dataclass(frozen=True)
class VendorAuthMetadata:
    """OAuth metadata sourced from the per-vendor OAuth sources.

    Holds endpoints/scopes/profile namespace only; it never carries credentials.
    """

    authorization_endpoint: str | None
    token_endpoint: str | None
    scopes: tuple[str, ...]
    profile_namespace: str


# Per-vendor OAuth metadata, referencing the existing OAuth-source constants
# rather than duplicating endpoint/scope literals. Google resolves credentials
# via ADC/service-account (no static authorization/token endpoints), so those
# fields are ``None`` and only scopes/profile namespace are exposed.
_VENDOR_AUTH_METADATA = {
    "anthropic": VendorAuthMetadata(
        authorization_endpoint=ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT,
        token_endpoint=ANTHROPIC_OAUTH_TOKEN_ENDPOINT,
        scopes=tuple(ANTHROPIC_OAUTH_SCOPES),
        profile_namespace="anthropic:subscription",
    ),
    "openai": VendorAuthMetadata(
        authorization_endpoint=OPENAI_OAUTH_AUTHORIZATION_ENDPOINT,
        token_endpoint=OPENAI_OAUTH_TOKEN_ENDPOINT,
        scopes=tuple(OPENAI_OAUTH_SCOPES),
        profile_namespace="openai:subscription",
    ),
    "google": VendorAuthMetadata(
        authorization_endpoint=None,
        token_endpoint=None,
        scopes=tuple(GEMINI_OAUTH_SCOPES),
        profile_namespace="google:vertex",
    ),
}


@dataclass(frozen=True)
class VendorProfile:
    """Read-only metadata facade for one model vendor.

    Composes registry identity/catalog and OAuth-source ``auth_metadata``.
    Owns metadata only: no acquisition, no invocation, no network.
    """

    vendor: str
    identity: VendorIdentity
    model_catalog: VendorModelCatalog
    auth_metadata: VendorAuthMetadata

    def normalize_model_name(self, name: str) -> str:
        """Return the canonical model id, dropping any ``vendor/`` prefix."""
        return name.split("/", 1)[1] if "/" in name else name

    def classify_error(self, exc: Exception) -> ErrorCategory:
        """Classify a vendor error into a small stable category set.

        Composes over the transport-level status code carried by
        :class:`ProviderTransportError`. Non-transport exceptions are
        ``"unknown"``.
        """
        if not isinstance(exc, ProviderTransportError):
            return "unknown"
        status_code = exc.status_code
        if status_code is None:
            return "transient" if exc.retryable else "unknown"
        if status_code in {401, 403}:
            return "auth"
        if status_code == 429:
            return "rate_limit"
        if status_code >= 500:
            return "transient"
        if status_code >= 400:
            return "invalid_request"
        return "unknown"


def vendor_profile(
    vendor: str,
    *,
    registry: ModelProviderRegistry | None = None,
) -> VendorProfile:
    """Build the read-only :class:`VendorProfile` for one vendor.

    ``vendor`` accepts the canonical tokens ``anthropic``/``openai``/``google``
    and the legacy ``gemini`` alias (normalized to ``google``). Unknown vendors
    raise :class:`ValueError`.
    """
    canonical = normalize_provider_family(vendor)
    provider_id = _VENDOR_PROVIDER_IDS.get(canonical)
    if provider_id is None:
        raise ValueError(f"unknown vendor: {vendor!r}")

    resolved_registry = registry or default_model_provider_registry()
    provider = resolved_registry.require(provider_id)

    identity = VendorIdentity(
        provider_id=provider.id,
        display_name=provider.name,
        provider_family=provider.provider,
    )
    model_catalog = _model_catalog_from_provider_metadata(provider.metadata)
    auth_metadata = _VENDOR_AUTH_METADATA[canonical]

    return VendorProfile(
        vendor=canonical,
        identity=identity,
        model_catalog=model_catalog,
        auth_metadata=auth_metadata,
    )


def _model_catalog_from_provider_metadata(metadata: dict[str, object]) -> VendorModelCatalog:
    """Compose a model catalog from the registry provider's metadata.

    Reads the registry's ``default_model`` (and any sibling model keys such as
    ``opus_model``) rather than hardcoding a model list.
    """
    default_model = metadata.get("default_model")
    if not isinstance(default_model, str) or not default_model:
        raise ValueError("provider metadata is missing a default_model")
    models = [default_model]
    for key, value in metadata.items():
        if key == "default_model":
            continue
        if key.endswith("_model") and isinstance(value, str) and value and value not in models:
            models.append(value)
    return VendorModelCatalog(default_model=default_model, models=tuple(models))


__all__ = [
    "VendorAuthMetadata",
    "VendorIdentity",
    "VendorModelCatalog",
    "VendorProfile",
    "vendor_profile",
]
