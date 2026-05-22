"""Auth profile visibility helpers."""

from __future__ import annotations

from collections.abc import Iterable

from craik.runtime.auth.operator import (
    OperatorSession,
    OperatorSessionNotFoundError,
    OperatorSessionStore,
)
from craik.runtime.auth.profile import AuthProfile


def active_operator_session_from_env() -> OperatorSession | None:
    """Return the active operator session, or None when unauthenticated."""
    try:
        return OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        return None


def visible_auth_profiles(
    profiles: Iterable[AuthProfile],
    session: OperatorSession | None,
) -> list[AuthProfile]:
    """Return profiles visible to the active operator session."""
    return [
        profile
        for profile in profiles
        if session is None or auth_profile_visible_to(profile, session.subject, session.groups)
    ]


def auth_profile_visible_to(
    profile: AuthProfile,
    operator_subject: str,
    operator_groups: list[str],
) -> bool:
    """Return whether an operator may see or select a profile."""
    if profile.authorized_operators is None and profile.authorized_operator_groups is None:
        return True
    if profile.authorized_operators and operator_subject in profile.authorized_operators:
        return True
    allowed_groups = set(profile.authorized_operator_groups or [])
    return bool(allowed_groups.intersection(operator_groups))
