"""Operator session contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from craik.contracts.models import CraikModel


class OperatorSession(CraikModel):
    """Normalized OIDC-authenticated operator identity."""

    subject: str
    email: str | None = None
    display_name: str | None = None
    groups: list[str] = Field(default_factory=list)
    issuer: str
    id_token_jti: str
    expires_at: datetime
    refresh_token_ref: str | None = None
    dashboard_binding_token: str | None = None
