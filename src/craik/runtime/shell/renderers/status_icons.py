"""Status-icon constants and lookup."""

STATUS_OK = "✓"
STATUS_FAIL = "✗"
STATUS_WARN = "⚠"
STATUS_PENDING = "◌"

_STATUS_MAP = {
    "ok": STATUS_OK,
    "true": STATUS_OK,
    "configured": STATUS_OK,
    "ready": STATUS_OK,
    "active": STATUS_OK,
    "success": STATUS_OK,
    "fail": STATUS_FAIL,
    "false": STATUS_FAIL,
    "missing": STATUS_FAIL,
    "unconfigured": STATUS_FAIL,
    "failed": STATUS_FAIL,
    "error": STATUS_FAIL,
    "warning": STATUS_WARN,
    "warn": STATUS_WARN,
    "pending": STATUS_PENDING,
    "loading": STATUS_PENDING,
    "unknown": STATUS_PENDING,
}


def icon_for_bool(value: bool) -> str:
    """Return the canonical status icon for a boolean."""
    return STATUS_OK if value else STATUS_FAIL


def icon_for_status(status: str) -> str:
    """Return the canonical status icon for a named status."""
    return _STATUS_MAP.get(status.lower(), STATUS_PENDING)
