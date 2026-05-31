"""Adapter seam foundation: `RunContext` and the `Adapter` protocol.

This module is intentionally tiny and dependency-free beyond the Phase-1 event
type. Concrete adapters (CLI / API families) live in sibling modules and are
registered through ``select_adapter``; each concrete adapter holds its own
``VendorProfile`` injected at construction by ``select_adapter`` -- the profile
is deliberately NOT part of ``RunContext``.
"""

from __future__ import annotations

import abc
import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from craik.runtime.backend.events import BackendEvent

# Envelope schema sections that must never leak into emitted events. The vendor
# paths declare these as expected runner outputs; adapters strip any matching
# markers so they stay an internal contract concern. Shared by every adapter so
# the strip logic is defined once, not copied per vendor.
_CONTRACT_ENVELOPE_MARKERS = ("craik.runner_step_result", "craik.handoff")


def strip_contract_envelopes(text: str) -> str:
    """Remove ``craik.runner_step_result`` / ``craik.handoff`` envelope markers.

    The vendor paths use these schema ids as expected runner outputs; they are
    an internal contract concern and must never surface in emitted events.
    Tolerates repeated markers and collapses surrounding whitespace.
    """
    cleaned = text
    for marker in _CONTRACT_ENVELOPE_MARKERS:
        cleaned = cleaned.replace(marker, "")
    return " ".join(cleaned.split())


def optional_str(value: Any) -> str | None:
    """Coerce ``value`` to a trimmed non-empty string, or ``None``.

    Shared by adapters mapping native fields that may be absent/blank into
    optional event attributes.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class RunContext:
    """Per-run inputs handed to an adapter's ``run`` method.

    ``decide`` maps a tool-request dict to ``"allow"`` / ``"deny"``. It is used
    by ``APIAdapter.run``'s tool-loop directly, and by the CLI hook bridge
    (Phase 5) to resolve a hook callback.
    """

    prompt: str
    env: dict[str, str]
    emit: Callable[[BackendEvent], None]
    decide: Callable[[dict[str, Any]], str]
    require_operator_approval: bool


class Adapter(Protocol):
    """Structural protocol implemented by every concrete backend adapter."""

    vendor: str  # "anthropic" | "openai" | "google"
    surface: str  # "cli" | "api"

    def supports_live_gating(self) -> bool:
        """Whether this adapter can gate tool calls before they execute."""

    def auth_source(self) -> str:
        """Name the auth profile/source identifier this adapter uses.

        Metadata only -- this records auth provenance for the seam; it does NOT
        acquire credentials.
        """

    def run(self, ctx: RunContext) -> Iterable[BackendEvent]:
        """Run the prompt described by ``ctx`` and yield canonical events."""


# --- Family bases (template method) -----------------------------------------
# `CLIAdapter` and `APIAdapter` are ABSTRACT bases implementing the `Adapter`
# protocol via the template-method pattern. Concrete per-vendor adapters
# (`AnthropicCLI`, `OpenAIAPI`, ...) land in Phase 4 and subclass these,
# filling in the abstract hooks. The bases own the run-shaping orchestration --
# crucially, on the API side they own the governed tool list so no vendor
# hosted/server-side tool can bypass craik's per-tool veto.


class CLIAdapter(abc.ABC):
    """Abstract base for CLI-surface adapters that spawn a vendor subprocess.

    The ``run`` template builds a command, spawns the process (a hook -- the
    base never hardcodes a real subprocess), reads native stdout lines, and
    maps each parsed native event to a canonical ``BackendEvent``. Emission is
    NOT the base's job: ``run`` *yields* events; the seam emits them.
    """

    vendor: str
    surface: str

    def supports_live_gating(self) -> bool:
        """CLI adapters gate at the tool/hook boundary by default.

        The real per-vendor truth lands in Phase 4 (e.g. ``OpenAICLI`` will
        override this to ``False``); the base default is the permissive case.
        """
        return True

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """Template: build command -> spawn -> parse stream -> yield events."""
        cmd = self.build_command(ctx)
        lines = self.spawn(cmd, ctx.env)
        yield from self.parse_stream(lines, ctx)

    def parse_stream(self, lines: Iterable[str], ctx: RunContext) -> Iterator[BackendEvent]:
        """Default: JSON-decode each non-empty line and map it to an event.

        Small and overridable -- a subclass with a non-JSON native stream can
        replace this wholesale while still reusing ``run``.
        """
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            native: dict[str, Any] = json.loads(stripped)
            event = self.map_native_event(native)
            if event is not None:
                yield event

    @abc.abstractmethod
    def build_command(self, ctx: RunContext) -> list[str]:
        """Return the argv for the vendor CLI for this run."""

    @abc.abstractmethod
    def spawn(self, cmd: list[str], env: dict[str, str]) -> Iterable[str]:
        """Run ``cmd`` and return an iterable of native stdout lines.

        In real adapters this wraps a subprocess; the base only calls the hook
        so it stays free of any real process or IO dependency.
        """

    @abc.abstractmethod
    def map_native_event(self, native: dict[str, Any]) -> BackendEvent | None:
        """Map ONE parsed native event to a ``BackendEvent``, or None to drop."""


class APIAdapter(abc.ABC):
    """Abstract base for API-surface adapters driving the craik tool-loop.

    The ``run`` template owns the agentic loop: request the model, surface
    events, and -- for every tool the model wants to call -- consult
    ``ctx.decide`` BEFORE executing. Only on ``"allow"`` is the tool executed
    (via the ``execute_tool`` hook); a ``"deny"`` threads a denial result back
    to the model instead.

    Governance-critical: the base owns the tool list. ``function_tools`` returns
    ONLY caller-executed ``type=="function"`` specs; vendor hosted/server-side
    tools (OpenAI ``web_search`` / ``code_interpreter`` / ``file_search`` /
    ``computer_use`` / hosted-MCP, and the Gemini/Anthropic equivalents) are
    stripped, because they execute server-side and ungated and would bypass
    craik's veto. The only escape is an explicit, audited ``allow_hosted_tools``
    opt-out.
    """

    vendor: str
    surface: str

    def __init__(self) -> None:
        # Subclasses MUST call super().__init__(). The tool registry and the
        # opt-out flag are per-instance state owned by the base.
        self.registered_tools: list[dict[str, Any]] = []
        self.allow_hosted_tools: bool = False

    def supports_live_gating(self) -> bool:
        """Custom function tools are gateable, so default is ``True``."""
        return True

    def register_tool(self, spec: dict[str, Any]) -> None:
        """Register one tool spec the model may call.

        Specs are NOT filtered here -- filtering happens at send time in
        ``_governed_tools`` so a single audited flag governs the whole list.
        """
        self.registered_tools.append(spec)

    def _governed_tools(self, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter ``specs`` to the governed tool list actually sent to a vendor.

        Pure and easily tested. When ``allow_hosted_tools`` is ``False`` (the
        safe default), only ``type=="function"`` specs survive -- every vendor
        hosted/server-side tool is stripped so it can never execute ungated.
        When the audited opt-out is ``True``, all dict specs pass through.
        """
        governed: list[dict[str, Any]] = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            if self.allow_hosted_tools or spec.get("type") == "function":
                governed.append(spec)
        return governed

    def function_tools(self) -> list[dict[str, Any]]:
        """Return the governed tool list to send on a request."""
        return self._governed_tools(self.registered_tools)

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """Template: drive the craik tool-loop with a per-tool veto gate."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": ctx.prompt}]
        while True:
            response = self.request(messages, tools=self.function_tools(), env=ctx.env)
            events, tool_calls = self.map_response(response)
            yield from events
            # No tool calls -> the model is done; end the loop.
            if not tool_calls:
                break
            for tool_call in tool_calls:
                decision = ctx.decide(tool_call)
                if decision == "allow":
                    result = self.execute_tool(tool_call)
                    messages.append({"role": "tool", "content": result})
                else:
                    # Denied: thread a denial result back so the model can
                    # adapt instead of stalling. The tool is NOT executed.
                    messages.append(
                        {
                            "role": "tool",
                            "content": {
                                "tool_call_id": tool_call.get("id"),
                                "decision": "deny",
                                "error": "denied by craik governance",
                            },
                        }
                    )

    @abc.abstractmethod
    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        env: dict[str, str],
    ) -> Any:
        """Send one model request and return the raw vendor response."""

    @abc.abstractmethod
    def map_response(self, response: Any) -> tuple[list[BackendEvent], list[dict[str, Any]]]:
        """Map a raw response to (events, tool_calls)."""

    @abc.abstractmethod
    def execute_tool(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Execute one ALLOWED tool call and return its result payload."""

    @abc.abstractmethod
    def auth_headers(self, env: dict[str, str]) -> dict[str, str]:
        """Return auth headers for vendor requests (the auth seam).

        Concrete adapters source these from their ``VendorProfile`` (Phase 3);
        the base deliberately neither imports nor references it.
        """
