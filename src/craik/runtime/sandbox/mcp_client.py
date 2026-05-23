"""MCP client configuration and routing compatibility."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel

MCPClientTransport = Literal["stdio", "http", "sse"]
MCPRouteKind = Literal["provider", "tool"]
MCPClientCompatibilityStatus = Literal["compatible", "blocked"]
_ALLOWED_MCP_URL_SCHEMES = frozenset({"http", "https"})


class MCPClientConfig(CraikModel):
    """Non-secret MCP client configuration."""

    id: str
    name: str
    transport: MCPClientTransport
    server_ref: str
    endpoint_ref: str | None = None
    command_ref: str | None = None
    config_refs: list[str] = Field(default_factory=list)
    secret_ref_names: list[str] = Field(default_factory=list)
    policy_envelope_id: str | None = None
    grant_required: bool = True
    receipt_required: bool = True
    redaction_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    docs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mcp_client_config(self) -> MCPClientConfig:
        """Keep MCP client config non-secret and policy-bound."""
        if self.transport in {"http", "sse"} and not self.endpoint_ref:
            raise ValueError(f"{self.transport} MCP clients require endpoint_ref")
        if self.transport == "stdio" and not self.command_ref:
            raise ValueError("stdio MCP clients require command_ref")
        if not self.grant_required:
            raise ValueError("MCP clients require capability grants")
        if not self.receipt_required:
            raise ValueError("MCP clients require receipts")
        if not self.redaction_required:
            raise ValueError("MCP clients require redaction")
        _reject_secret_like_values(self.server_ref, "server_ref")
        for value, field_name in (
            (self.endpoint_ref, "endpoint_ref"),
            (self.command_ref, "command_ref"),
        ):
            if value is not None:
                _reject_secret_like_values(value, field_name)
        _reject_secret_like_metadata(self.metadata)
        return self


class MCPClientRoute(CraikModel):
    """Provider or tool route through an MCP client."""

    id: str
    client_id: str
    kind: MCPRouteKind
    target_ref: str
    capability: str
    grant_required: bool = True
    receipt_required: bool = True
    audit_label: str | None = None


class MCPClientCompatibility(CraikModel):
    """Compatibility result for MCP client routing."""

    status: MCPClientCompatibilityStatus
    compatible: bool
    client_id: str
    reasons: list[str] = Field(default_factory=list)
    route_ids: list[str] = Field(default_factory=list)
    required_controls: list[str] = Field(default_factory=list)


def mcp_client_compatibility(
    client: MCPClientConfig,
    routes: list[MCPClientRoute],
) -> MCPClientCompatibility:
    """Validate MCP client route compatibility with Craik policy boundaries."""
    reasons: list[str] = []
    if not routes:
        reasons.append("MCP clients require at least one provider or tool route")
    for route in routes:
        if route.client_id != client.id:
            reasons.append(f"route {route.id} belongs to {route.client_id}, not {client.id}")
        if not route.grant_required:
            reasons.append(f"route {route.id} does not require a capability grant")
        if not route.receipt_required:
            reasons.append(f"route {route.id} does not require receipts")
    controls = ["redaction", "capability_grants", "receipts"]
    if client.secret_ref_names:
        controls.append("external_secret_refs")
    if client.policy_envelope_id:
        controls.append("policy_envelope")
    if reasons:
        return MCPClientCompatibility(
            status="blocked",
            compatible=False,
            client_id=client.id,
            reasons=reasons,
            route_ids=[route.id for route in routes],
            required_controls=controls,
        )
    return MCPClientCompatibility(
        status="compatible",
        compatible=True,
        client_id=client.id,
        reasons=["MCP client routes are grant-, receipt-, and redaction-ready"],
        route_ids=[route.id for route in routes],
        required_controls=controls,
    )


def _reject_secret_like_values(value: str, field_name: str) -> None:
    split = urlsplit(value)
    if split.scheme and split.scheme.lower() not in _ALLOWED_MCP_URL_SCHEMES:
        raise ValueError(f"{field_name} must use http or https URL scheme")
    if split.username or split.password:
        raise ValueError(f"{field_name} must not contain credentials")
    secret_tokens = ("token=", "api_key=", "apikey=", "password=", "secret=")
    normalized = value.lower()
    if any(token in normalized for token in secret_tokens):
        raise ValueError(f"{field_name} must not contain secret-like query values")


def _reject_secret_like_metadata(metadata: dict[str, Any]) -> None:
    secret_tokens = ("secret", "token", "api_key", "apikey", "password", "credential")
    for key in metadata:
        normalized = key.lower().replace("-", "_")
        if any(token in normalized for token in secret_tokens):
            raise ValueError("MCP client metadata must not contain secret-like keys")
