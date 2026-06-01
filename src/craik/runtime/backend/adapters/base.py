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

from craik.runtime.backend.events import (
    BackendEvent,
    EventSource,
    ReceiptDecidedBy,
    ReceiptDecision,
    ReceiptMode,
    approval_resolved_event,
    receipt_event,
)

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


@dataclass(frozen=True)
class ReceiptPosture:
    """Static governance posture an API adapter stamps on every receipt event.

    Each concrete ``APIAdapter`` declares a class-level ``posture`` so the base
    ``run`` loop can emit receipt events without per-vendor branching: the
    ``source`` (originating adapter), the ``execution`` model (``"craik"`` when
    craik ran the tool itself via the side-effects layer), the permission
    ``mode``, and who ``decided_by``. Frozen because the posture is a fixed trait
    of the adapter, not per-run state.
    """

    source: EventSource
    execution: str
    mode: ReceiptMode
    decided_by: ReceiptDecidedBy


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
    # Concrete adapters declare a class-level posture; the base run loop stamps
    # it onto every emitted receipt event. ``None`` keeps a posture-less adapter
    # (e.g. a minimal test fake) on the silent loop -- it threads messages and
    # emits no receipt events.
    posture: ReceiptPosture | None = None

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
        """Default API entry point: the direct-HTTP governed tool-loop.

        Two distinct API run paths exist (Task 5.5a documents the split):

        * ``direct_tool_loop`` -- the live-NETWORK gate->request->map_response->
          execute_tool loop owned here by the base. It is the fixture-tested
          design (the Phase-4 ``*API`` unit tests + ``test_family_bases`` drive
          it) and the path a posture-less fake/test adapter uses. It is NOT the
          live provider path.
        * the provider-CORE path -- the concrete ``*API`` adapters OVERRIDE
          ``run`` to compose ``audited_core.run_provider_typed`` (the proven
          provider execution + persistence the legacy provider layer uses) and
          emit typed events from its result. That is the live-today path.

        The base ``run`` defaults to ``direct_tool_loop`` so a non-overriding
        adapter (e.g. ``FakeAPIAdapter``) still loops; concrete live adapters
        override ``run`` and keep ``direct_tool_loop`` available for their loop
        tests.
        """
        return self.direct_tool_loop(ctx)

    def direct_tool_loop(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """The direct-HTTP governed tool-loop shared by every API adapter.

        Per turn: request the model, map to (events, tool_calls), yield the
        events, and -- for each requested tool -- consult ``ctx.decide`` BEFORE
        executing.

        * ``allow`` runs ``execute_tool`` (which routes through the gated
          side-effects layer and returns the standardized
          ``{"allowed", "receipt_id", "output", "tool_call_id"}`` dict). The
          emitted receipt event then reflects the side-effects layer's ACTUAL
          ``allowed`` verdict via ``_receipt_event`` -- NOT just ``ctx.decide`` --
          so a decision-source disagreement (gate veto despite an ``allow``
          decision) emits a ``deny`` receipt matching the persisted denial.
        * ``deny`` skips execution entirely and yields ``_events_for_denied``.

        The tool-result message threaded back to the model carries ONLY the
        redacted ``output`` (never the craik-internal ``receipt_id``), with the
        ``tool_call_id`` for multi-tool correlation.
        """
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
                    yield from self._receipt_event(tool_call, result)
                    messages.append(self._tool_result_message(tool_call, result))
                else:
                    # Denied: NOT executed. Emit the governance events and thread
                    # a denial result back so the model can adapt instead of stall.
                    yield from self._events_for_denied(tool_call)
                    messages.append(self._denial_message(tool_call))

    def _receipt_event(
        self,
        tool_call: dict[str, Any],
        result: dict[str, Any],
    ) -> list[BackendEvent]:
        """Emit the receipt event reflecting the side-effects layer's verdict.

        Branches on ``result["allowed"]`` -- the gate's ACTUAL verdict, not the
        ``ctx.decide`` decision. When the gate allowed the effect, a ``decision=
        "allow"`` receipt is emitted with the persisted receipt id; when the gate
        vetoed despite an ``allow`` decision, a ``decision="deny"`` receipt is
        emitted carrying the DENIAL receipt id (and no allow event). Either way
        the ``tool_call_id`` rides on the event ``data`` for multi-tool
        correlation. A posture-less adapter emits nothing (fake/test path).
        """
        posture = self.posture
        if posture is None:
            return []
        allowed = bool(result.get("allowed"))
        decision: ReceiptDecision = "allow" if allowed else "deny"
        decided_by: ReceiptDecidedBy = posture.decided_by if allowed else "policy"
        receipt_id = str(result.get("receipt_id") or "receipt_api_run")
        event = receipt_event(
            receipt_id=receipt_id,
            source=posture.source,
            purpose="execution",
            execution=posture.execution,  # type: ignore[arg-type]
            mode=posture.mode,
            decision=decision,
            decided_by=decided_by,
        )
        event.data["tool_call_id"] = result.get("tool_call_id") or tool_call.get("id")
        return [event]

    def _events_for_denied(self, tool_call: dict[str, Any]) -> list[BackendEvent]:
        """Governance events for a tool vetoed at the decision gate (no exec).

        Default: a resolved-as-deny ``approval`` event plus a ``deny``
        ``receipt.created``. Overridable per adapter; a posture-less adapter
        emits nothing.
        """
        posture = self.posture
        if posture is None:
            return []
        approval_id = optional_str(tool_call.get("id")) or "approval_api_denied"
        deny_receipt = receipt_event(
            receipt_id=f"receipt_denied_{approval_id}",
            source=posture.source,
            purpose="execution",
            execution=posture.execution,  # type: ignore[arg-type]
            mode=posture.mode,
            decision="deny",
            decided_by="policy",
        )
        deny_receipt.data["tool_call_id"] = tool_call.get("id")
        return [
            approval_resolved_event(
                approval_id=approval_id,
                decision="deny",
                source=posture.source,
                decided_by="policy",
            ),
            deny_receipt,
        ]

    @staticmethod
    def _tool_result_message(
        tool_call: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Thread the tool result back to the model.

        Carries ONLY the redacted ``output`` plus the ``tool_call_id`` -- never
        the craik-internal ``receipt_id`` (which must not leak into model
        context).
        """
        return {
            "role": "tool",
            "tool_call_id": result.get("tool_call_id") or tool_call.get("id"),
            "content": result.get("output"),
        }

    @staticmethod
    def _denial_message(tool_call: dict[str, Any]) -> dict[str, Any]:
        """Thread a denial result back so the model can adapt instead of stall."""
        return {
            "role": "tool",
            "content": {
                "tool_call_id": tool_call.get("id"),
                "decision": "deny",
                "error": "denied by craik governance",
            },
        }

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
        """Execute one ALLOWED tool call via the gated side-effects layer.

        MUST return the standardized dict the base ``run`` loop consumes::

            {
                "allowed": bool,        # the side-effects layer's ACTUAL verdict
                "receipt_id": str | None,  # persisted receipt id (allow or deny)
                "output": <redacted>,   # threaded to the model; NEVER the dict
                "tool_call_id": str,    # for multi-tool correlation
            }

        ``allowed`` is the gate's verdict and MAY be ``False`` even though
        ``ctx.decide`` said allow (a decision-source disagreement); the base
        reconciles this so the emitted receipt reflects the persisted truth.
        """

    @abc.abstractmethod
    def auth_headers(self, env: dict[str, str]) -> dict[str, str]:
        """Return auth headers for vendor requests (the auth seam).

        Concrete adapters source these from their ``VendorProfile`` (Phase 3);
        the base deliberately neither imports nor references it.
        """
