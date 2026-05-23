"""Dashboard authentication helpers."""

from __future__ import annotations

import secrets
from typing import Any

from craik.runtime.auth.operator import (
    OperatorSession,
    OperatorSessionNotFoundError,
    OperatorSessionStore,
)


def dashboard_authorized(
    headers: Any,
    query: dict[str, list[str]],
    auth_token: str | None,
    *,
    env: dict[str, str] | None,
) -> bool:
    """Return whether one dashboard request has valid dashboard credentials."""
    supplied = headers.get("X-Craik-Dashboard-Token")
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        supplied = auth.removeprefix("Bearer ")
    if query.get("token"):
        supplied = query["token"][0]
    if auth_token and secrets.compare_digest(supplied or "", auth_token):
        return True
    if auth_token is None:
        return _operator_session_authorized(headers, env)
    return False


def dashboard_auth_failure_payload(
    headers: Any,
    query: dict[str, list[str]],
    auth_token: str | None,
    *,
    env: dict[str, str] | None,
) -> dict[str, object]:
    """Return the redacted dashboard auth failure body."""
    if (
        auth_token is None
        and not headers.get("X-Craik-Dashboard-Token")
        and not headers.get("Authorization", "").startswith("Bearer ")
        and not query.get("token")
        and operator_session_requires_relogin(env)
    ):
        return {
            "error": "dashboard authentication required",
            "remediation": "stale session, re-login required",
        }
    return {"error": "dashboard authentication required"}


def has_operator_session(env: dict[str, str] | None) -> bool:
    """Return whether an operator session is active."""
    return active_operator_session(env) is not None


def operator_session_requires_relogin(env: dict[str, str] | None) -> bool:
    """Return whether a legacy session lacks dashboard binding material."""
    session = active_operator_session(env)
    return session is not None and not session.dashboard_binding_token


def active_operator_session(env: dict[str, str] | None) -> OperatorSession | None:
    """Return the active operator session if one can be loaded."""
    try:
        return OperatorSessionStore.from_env(env).get()
    except OperatorSessionNotFoundError:
        return None


def _operator_session_authorized(headers: Any, env: dict[str, str] | None) -> bool:
    session = active_operator_session(env)
    if session is None or not session.dashboard_binding_token:
        return False
    supplied = headers.get("X-Craik-Operator-Session")
    return secrets.compare_digest(supplied or "", session.dashboard_binding_token)
