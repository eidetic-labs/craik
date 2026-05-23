"""Operator-mode switches shared by readiness and CLI guards."""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}


def operator_session_required(env: dict[str, str] | None = None) -> bool:
    """Return whether audited multi-operator mode requires OIDC operator login."""
    values = os.environ if env is None else env
    return values.get("CRAIK_OPERATOR_REQUIRED", "").strip().lower() in _TRUTHY


def is_audit_reduced_mode(env: dict[str, str] | None = None) -> bool:
    """Return whether Craik is running without mandatory operator session binding."""
    return not operator_session_required(env)
