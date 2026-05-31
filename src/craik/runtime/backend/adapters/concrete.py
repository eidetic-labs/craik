"""Concrete per-vendor adapter stubs (Phase 2 placeholders).

These six classes exist so ``select_adapter`` has something to instantiate and
return for each canonical ``"<vendor>-<surface>"`` id. They are deliberately
minimal: each implements the ``Adapter`` protocol structurally but its ``run``
raises ``NotImplementedError``.

Phase 4 will rebase these onto ``CLIAdapter`` / ``APIAdapter`` and implement
real behavior (per-vendor ``supports_live_gating`` truth, native-event mapping,
the governed tool-loop, etc.); Task 2.4 will add a ``_legacy_run`` to
``AnthropicCLI`` / ``AnthropicAPI``. Keep them minimal until then.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.events import BackendEvent

if TYPE_CHECKING:
    from craik.runtime.backend.session import BackendPromptResult


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

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        # A normal method that raises on call -- NOT a generator. Raising
        # immediately is the desired behavior for these Phase-2 stubs.
        raise NotImplementedError(f"{type(self).__name__}.run is not implemented until Phase 4")


class AnthropicCLI(_NotImplementedAdapter):
    vendor = "anthropic"
    surface = "cli"

    def _legacy_run(
        self,
        ctx: RunContext,
        *,
        events: list[BackendEvent],
        source: str,
        env: dict[str, str] | None,
    ) -> BackendPromptResult:
        """Bridge to the legacy claude-code path (Task 2.4 seam).

        ``source`` is accepted for signature symmetry with ``AnthropicAPI`` but
        is unused by the claude path. ``env`` is the ORIGINAL value (possibly
        None) -- threaded separately from ``ctx.env`` to preserve byte-identical
        behavior.
        """
        # Lazy import: `legacy_runs` imports `session`, which (lazily) imports
        # `registry` -> `concrete`; keeping this function-local avoids a cycle.
        from craik.runtime.backend.adapters.legacy_runs import _legacy_claude_code_run

        return _legacy_claude_code_run(
            prompt=ctx.prompt,
            env=env,
            emit=ctx.emit,
            events=events,
            require_operator_approval=ctx.require_operator_approval,
        )


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
