"""Concrete per-vendor adapter stubs (Phase 2 placeholders).

These classes exist so ``select_adapter`` has something to instantiate and
return for each canonical ``"<vendor>-<surface>"`` id. The remaining stubs are
deliberately minimal: each implements the ``Adapter`` protocol structurally but
its ``run`` raises ``NotImplementedError``.

Phase 4 rebases these onto ``CLIAdapter`` / ``APIAdapter`` one vendor at a time.
The real :class:`AnthropicCLI` now lives in ``adapters.anthropic_cli`` (Task
4.1) and is re-exported here for back-compat so existing
``from ...concrete import AnthropicCLI`` imports keep resolving; the other five
remain stubs until their own Phase-4 tasks land.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.events import BackendEvent

if TYPE_CHECKING:
    from craik.runtime.backend.session import BackendPromptResult

__all__ = [
    "AnthropicAPI",
    "AnthropicCLI",
    "GoogleAPI",
    "GoogleCLI",
    "OpenAIAPI",
    "OpenAICLI",
]


class _NotImplementedAdapter:
    """Structural ``Adapter`` whose ``run`` raises until Phase 4.

    Subclasses set ``vendor`` / ``surface`` class attributes.
    """

    vendor: str
    surface: str

    def supports_live_gating(self) -> bool:
        # Sensible permissive default; the real per-vendor truth (e.g.
        # ``OpenAICLI`` observe-only -> ``False``) lands in Phase 4.
        return True

    def auth_source(self) -> str:
        # Metadata-only default until each vendor's Phase-4 task names its real
        # auth profile/source. Satisfies the ``Adapter`` protocol; acquires no
        # credentials.
        return f"{self.vendor}_unconfigured"

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        # A normal method that raises on call -- NOT a generator. Raising
        # immediately is the desired behavior for these Phase-2 stubs.
        raise NotImplementedError(f"{type(self).__name__}.run is not implemented until Phase 4")


class AnthropicAPI(_NotImplementedAdapter):
    vendor = "anthropic"
    surface = "api"

    def _legacy_run(
        self,
        ctx: RunContext,
        *,
        events: list[BackendEvent],
        source: str,
        env: dict[str, str] | None,
    ) -> BackendPromptResult:
        """Bridge to the legacy provider path (Task 2.4 seam).

        ``env`` is the ORIGINAL value (possibly None) -- threaded separately
        from ``ctx.env`` to preserve byte-identical behavior.
        """
        from craik.runtime.backend.adapters.legacy_runs import _legacy_provider_run

        return _legacy_provider_run(
            prompt=ctx.prompt,
            env=env,
            emit=ctx.emit,
            events=events,
            source=source,  # type: ignore[arg-type]
        )


class OpenAICLI(_NotImplementedAdapter):
    vendor = "openai"
    surface = "cli"


class OpenAIAPI(_NotImplementedAdapter):
    vendor = "openai"
    surface = "api"


class GoogleCLI(_NotImplementedAdapter):
    vendor = "google"
    surface = "cli"


class GoogleAPI(_NotImplementedAdapter):
    vendor = "google"
    surface = "api"
