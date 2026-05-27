"""In-process client for the local Craik Gateway session."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.session import BackendPromptResult, PromptSource, execute_prompt


@dataclass(frozen=True)
class GatewaySessionClient:
    """Client-facing wrapper around the local Gateway session boundary."""

    env: dict[str, str] | None = None
    source: PromptSource = "tui"
    event_handler: Callable[[BackendEvent], None] | None = field(default=None)

    def submit_prompt(self, prompt: str) -> BackendPromptResult:
        """Submit one raw prompt through the audited Gateway path."""
        return execute_prompt(
            prompt,
            env=self.env,
            source=self.source,
            stream=self.event_handler,
        )


__all__ = ["GatewaySessionClient"]
