"""Stigmem-backed credential source."""

from __future__ import annotations

from dataclasses import dataclass

from craik.contracts.models import MemoryScope
from craik.runtime.auth.profile import CredentialStatus
from craik.runtime.memory.memory import StigmemClient, StigmemConfig
from craik.runtime.memory.memory_errors import StigmemRequestError
from craik.runtime.providers.provider_transport import ProviderFamily

STIGMEM_CREDENTIAL_RELATION = "craik:credential:value"


class StigmemCredentialError(RuntimeError):
    """Raised when a Stigmem-backed credential cannot resolve."""


@dataclass(frozen=True)
class StigmemCredentialSource:
    """Resolve provider credentials from a Stigmem fact."""

    client: StigmemClient
    entity: str
    scope: MemoryScope = "team"
    relation: str = STIGMEM_CREDENTIAL_RELATION

    @classmethod
    def from_config(
        cls,
        *,
        node_url: str,
        entity: str,
        api_key: str | None = None,
        scope: MemoryScope = "team",
        relation: str = STIGMEM_CREDENTIAL_RELATION,
        timeout_seconds: float = 5.0,
    ) -> StigmemCredentialSource:
        """Build a Stigmem credential source from profile metadata."""
        return cls(
            client=StigmemClient(
                StigmemConfig(
                    node_url=node_url,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )
            ),
            entity=entity,
            scope=scope,
            relation=relation,
        )

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider-specific headers from the resolved Stigmem credential."""
        secret = self._resolve_secret()
        if family == "anthropic":
            return {
                "anthropic-version": "2023-06-01",
                "x-api-key": secret,
            }
        if family == "gemini":
            return {"x-goog-api-key": secret}
        return {"Authorization": f"Bearer {secret}"}

    def status(self) -> CredentialStatus:
        """Check whether the Stigmem credential fact resolves without exposing it."""
        try:
            self._resolve_secret()
        except StigmemCredentialError as exc:
            return CredentialStatus(status="rejected", detail=str(exc))
        return CredentialStatus(status="ok")

    def _resolve_secret(self) -> str:
        try:
            facts = self.client.list_facts(
                entity=self.entity,
                relation=self.relation,
                scope=self.scope,
                limit=1,
            )
        except StigmemRequestError as exc:
            raise StigmemCredentialError("Stigmem credential reference could not resolve") from exc
        if not facts or not facts[0].value:
            raise StigmemCredentialError("Stigmem credential reference could not resolve")
        return facts[0].value
