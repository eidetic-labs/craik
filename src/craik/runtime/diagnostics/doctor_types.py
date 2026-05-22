"""Shared doctor payload types."""

from __future__ import annotations

from dataclasses import dataclass

DiagnosticStatus = str


@dataclass(frozen=True)
class DiagnosticCheck:
    """One diagnostic check result."""

    name: str
    status: DiagnosticStatus
    summary: str
    action: str | None = None

    def to_payload(self) -> dict[str, str | None]:
        """Return a JSON-ready diagnostic payload."""
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "action": self.action,
        }
