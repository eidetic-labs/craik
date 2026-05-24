"""Provider usage and quota helpers for operator-facing status surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

UsageTier = Literal["green", "yellow", "orange", "red", "unknown"]


@dataclass(frozen=True)
class TokenUsageStatus:
    """Token usage summary suitable for compact TUI status rendering."""

    used_tokens: int
    limit_tokens: int | None = None

    @property
    def tier(self) -> UsageTier:
        """Return the display tier for the current usage ratio."""
        if self.limit_tokens is None or self.limit_tokens <= 0:
            return "unknown"
        percent = (self.used_tokens / self.limit_tokens) * 100
        if percent >= 95:
            return "red"
        if percent >= 80:
            return "orange"
        if percent >= 50:
            return "yellow"
        return "green"

    @property
    def display(self) -> str:
        """Return a compact usage string such as ``12.4K/200K``."""
        used = _compact_number(self.used_tokens)
        if self.limit_tokens is None or self.limit_tokens <= 0:
            return f"{used} tokens"
        return f"{used}/{_compact_number(self.limit_tokens)}"


@dataclass(frozen=True)
class ProviderQuotaStatus:
    """Provider quota status suitable for compact TUI status rendering."""

    remaining_percent: int | None = None
    detail: str | None = None

    @property
    def available(self) -> bool:
        """Return whether quota information should be shown to the operator."""
        return self.remaining_percent is not None

    @property
    def tier(self) -> UsageTier:
        """Return the display tier for quota remaining."""
        if self.remaining_percent is None:
            return "unknown"
        if self.remaining_percent <= 5:
            return "red"
        if self.remaining_percent <= 20:
            return "orange"
        if self.remaining_percent <= 50:
            return "yellow"
        return "green"

    @property
    def display(self) -> str:
        """Return a compact quota string."""
        if self.remaining_percent is None:
            return self.detail or "quota unavailable"
        return f"{self.remaining_percent}% quota"


def hidden_quota_status(detail: str | None = None) -> ProviderQuotaStatus:
    """Return an intentionally hidden quota status for unavailable provider APIs."""
    return ProviderQuotaStatus(remaining_percent=None, detail=detail)


def quota_status_from_headers(
    *,
    status_code: int,
    headers: dict[str, str],
) -> ProviderQuotaStatus:
    """Build quota display data from provider rate-limit headers when available."""
    if status_code in {401, 403, 404}:
        return hidden_quota_status("provider quota is not available")
    if not (200 <= status_code < 300):
        return hidden_quota_status("provider quota check failed")
    normalized = {key.lower(): value for key, value in headers.items()}
    limit = _int_header(normalized, "x-ratelimit-limit-requests")
    remaining = _int_header(normalized, "x-ratelimit-remaining-requests")
    if limit is None or remaining is None or limit <= 0:
        return hidden_quota_status("provider quota headers are unavailable")
    percent = max(0, min(100, round((remaining / limit) * 100)))
    return ProviderQuotaStatus(remaining_percent=percent)


def _int_header(headers: dict[str, str], key: str) -> int | None:
    value = headers.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _compact_number(value: int) -> str:
    absolute = abs(value)
    sign = "-" if value < 0 else ""
    if absolute >= 1_000_000:
        return f"{sign}{absolute / 1_000_000:.1f}M".replace(".0M", "M")
    if absolute >= 1_000:
        return f"{sign}{absolute / 1_000:.1f}K".replace(".0K", "K")
    return str(value)
