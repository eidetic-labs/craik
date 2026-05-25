"""Shared identity and scope command results."""

from __future__ import annotations

from craik.runtime.auth import AuthProfileStore, AuthProfileStoreError
from craik.runtime.auth.operator import (
    OperatorSession,
    OperatorSessionNotFoundError,
    OperatorSessionStore,
    OperatorSessionStoreError,
)
from craik.runtime.auth.visibility import visible_auth_profiles
from craik.runtime.contract import CommandResult, NextAction


def who_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return active operator identity and visible auth scope summary."""
    session, session_error = _active_session(env)
    profile_summary, profile_error = _visible_profile_summary(session, env)
    payload: dict[str, object] = {
        "operator": _operator_payload(session),
        "auth_scope": profile_summary,
        "status": "authenticated" if session is not None else "unauthenticated",
        "warnings": [warning for warning in (session_error, profile_error) if warning],
    }
    next_actions: list[NextAction] = []
    if session is None:
        next_actions.append(
            NextAction(
                text="Start operator login",
                command="/login",
                field="operator",
            )
        )
    return CommandResult(
        payload=payload,
        shape="kv",
        text=_who_text(payload),
        next_actions=next_actions,
    )


def _active_session(
    env: dict[str, str] | None,
) -> tuple[OperatorSession | None, str | None]:
    try:
        return OperatorSessionStore.from_env(env).get(), None
    except OperatorSessionNotFoundError:
        return None, None
    except OperatorSessionStoreError as error:
        return None, str(error)


def _visible_profile_summary(
    session: OperatorSession | None,
    env: dict[str, str] | None,
) -> tuple[dict[str, object], str | None]:
    try:
        profiles = AuthProfileStore.from_env(env).list()
    except AuthProfileStoreError as error:
        return _empty_profile_summary(), str(error)

    visible = visible_auth_profiles(profiles, session)
    scoped = [
        profile
        for profile in profiles
        if profile.authorized_operators is not None
        or profile.authorized_operator_groups is not None
    ]
    return (
        {
            "visible_profiles": len(visible),
            "total_profiles": len(profiles),
            "scoped_profiles": len(scoped),
            "visible_profile_ids": sorted(profile.id for profile in visible),
        },
        None,
    )


def _empty_profile_summary() -> dict[str, object]:
    return {
        "visible_profiles": 0,
        "total_profiles": 0,
        "scoped_profiles": 0,
        "visible_profile_ids": [],
    }


def _operator_payload(session: OperatorSession | None) -> dict[str, object]:
    if session is None:
        return {
            "active": False,
            "subject": None,
            "display_name": None,
            "email": None,
            "issuer": None,
            "groups": [],
            "expires_at": None,
        }
    return {
        "active": True,
        "subject": session.subject,
        "display_name": session.display_name,
        "email": session.email,
        "issuer": session.issuer,
        "groups": session.groups,
        "expires_at": session.expires_at.isoformat(),
    }


def _who_text(payload: dict[str, object]) -> str:
    operator = payload["operator"]
    auth_scope = payload["auth_scope"]
    if not isinstance(operator, dict) or not isinstance(auth_scope, dict):
        return "Identity state is unavailable."
    if operator.get("active"):
        subject = operator.get("subject") or "unknown"
        display_name = operator.get("display_name")
        identity = f"{display_name} ({subject})" if display_name else str(subject)
        lines = [f"Operator: {identity}"]
        groups = operator.get("groups")
        if isinstance(groups, list) and groups:
            lines.append(f"Groups: {', '.join(str(group) for group in groups)}")
    else:
        lines = ["Operator: unauthenticated"]
    lines.extend(
        [
            f"Visible profiles: {auth_scope.get('visible_profiles', 0)}",
            f"Scoped profiles: {auth_scope.get('scoped_profiles', 0)}",
            f"Total profiles: {auth_scope.get('total_profiles', 0)}",
        ]
    )
    warnings = payload.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)
