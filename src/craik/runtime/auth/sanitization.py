"""Redaction helpers for auth status and diagnostics surfaces."""

from __future__ import annotations

import re

_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+")
_SECRET_ASSIGNMENT_RE = re.compile(r"(?i)(token|api_key|apikey|password|secret)=([^&\s]+)")


def sanitize_credential_error(error: BaseException) -> str:
    """Return bounded credential-source error detail without secret material."""
    detail = str(error) or "credential source failed"
    detail = _AUTH_HEADER_RE.sub(r"\1[redacted]", detail)
    detail = _SECRET_ASSIGNMENT_RE.sub(r"\1=[redacted]", detail)
    return detail[:200]
