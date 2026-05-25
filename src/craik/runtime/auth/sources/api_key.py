"""Environment-variable API-key credential source."""

from __future__ import annotations

from dataclasses import dataclass

from craik.runtime.auth.profile import CredentialStatus
from craik.runtime.auth.sources.anthropic_env import resolve_anthropic_credential_from_env
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.secrets import SecretNotFoundError, SecretRef, SecretResolver


@dataclass(frozen=True)
class EnvVarApiKeySource:
    """Resolve provider API keys from an environment variable at request time."""

    env_var: str
    resolver: SecretResolver = SecretResolver()

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider-specific headers for an API-key credential."""
        if family == "anthropic":
            credential = resolve_anthropic_credential_from_env(
                fallback_env_vars=(
                    "ANTHROPIC_TOKEN",
                    self.env_var,
                    "ANTHROPIC_API_KEY",
                    "CRAIK_ANTHROPIC_API_KEY",
                )
            )
            secret = credential.token if credential is not None else self._resolve_secret()
            headers = {"anthropic-version": "2023-06-01"}
            if secret:
                headers["x-api-key"] = secret
            return headers
        secret = self._resolve_secret()
        if family == "gemini":
            return {"x-goog-api-key": secret} if secret else {}
        if secret:
            return {"Authorization": f"Bearer {secret}"}
        return {}

    def status(self) -> CredentialStatus:
        """Check whether the configured environment credential can resolve."""
        if not self.env_var:
            return CredentialStatus(status="unknown", detail="no environment variable configured")
        try:
            if self.env_var in {
                "ANTHROPIC_TOKEN",
                "ANTHROPIC_API_KEY",
                "CRAIK_ANTHROPIC_API_KEY",
            }:
                credential = resolve_anthropic_credential_from_env(
                    fallback_env_vars=(
                        "ANTHROPIC_TOKEN",
                        self.env_var,
                        "ANTHROPIC_API_KEY",
                        "CRAIK_ANTHROPIC_API_KEY",
                    )
                )
                if credential is not None:
                    return CredentialStatus(status="ok", detail=credential.display)
            self._resolve_secret()
        except SecretNotFoundError:
            return CredentialStatus(status="rejected", detail="secret reference could not resolve")
        return CredentialStatus(status="ok")

    def _resolve_secret(self) -> str:
        if not self.env_var:
            return ""
        return self.resolver.resolve(SecretRef(env_var=self.env_var))
