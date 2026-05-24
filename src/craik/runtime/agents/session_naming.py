"""Session naming helpers shared by shell and persistent agents."""

from __future__ import annotations

import re

SESSION_NAME_MAX_LENGTH = 64
_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]+$")


class SessionNameError(ValueError):
    """Raised when a session display name is invalid."""


def validate_session_name(name: str) -> str:
    """Return a normalized session name or raise ``SessionNameError``."""
    if name != name.strip():
        raise SessionNameError("session name must not have leading or trailing whitespace")
    if not name:
        raise SessionNameError("session name must not be empty")
    if len(name) > SESSION_NAME_MAX_LENGTH:
        raise SessionNameError("session name must be 64 characters or fewer")
    if any(ord(character) < 32 for character in name):
        raise SessionNameError("session name must not contain control characters")
    if not _SESSION_NAME_RE.fullmatch(name):
        raise SessionNameError("session name may contain only letters, numbers, space, -, and _")
    return name
