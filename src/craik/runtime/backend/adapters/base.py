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

# --- Assistant-text cleaning (formatting-preserving) ------------------------
# The live model output interleaves prose the operator WANTS with a
# ``## Craik contract output`` section carrying ```json contract blocks the
# operator must NEVER see. The contract JSON may carry an empty ``"schema": ""``,
# so a marker-substring scrub alone misses the section. ``clean_assistant_text``
# strips the whole section via a line-based scanner ported from the Rust TUI's
# ``strip_craik_contract_output_sections`` (deleted in Phase 6 on a wrong
# assumption), then scrubs the markers, then normalizes whitespace WITHOUT
# flattening markdown -- newlines/lists/fences in the kept prose survive.

# Quoted contract keys that mark a line as part of a contract JSON body.
_CONTRACT_JSON_KEYS = (
    "schema",
    "task_id",
    "status",
    "summary",
    "evidence",
    "receipt_ids",
    "commands_run",
    "capabilities_used",
    "policy_compliance",
)
# Lone horizontal-rule separators a contract section may be preceded by.
_CONTRACT_SEPARATORS = ("---", "----", "-----", "***", "___", "—", "–")


# Envelope schema ids that must never leak into emitted events even when they
# appear OUTSIDE a detected contract section (e.g. a heading-less fenced block).
# Scrubbed as bare tokens; surrounding prose is preserved.
_CONTRACT_ENVELOPE_MARKERS = ("craik.runner_step_result", "craik.handoff")


def _contract_heading_kind(lower: str) -> str | None:
    """Classify a lowercased, trimmed line as a contract heading.

    Returns ``"group"`` for a ``## Craik contract output``-style heading (whose
    body is a GROUP of fenced blocks), ``"single"`` for an inline
    ``**craik.handoff**`` / ``craik.runner_step_result`` marker heading (a single
    fenced block), or ``None`` when the line is not a contract heading.
    """
    # Only a HEADING/label line can open a contract section -- never bare prose.
    # A markdown heading ("## ...") or a bold-only label line ("**...**").
    # Otherwise sentences that merely MENTION "contract output" (or start with
    # "craik.") would be silently eaten -- a false strip is worse than the wall.
    heading_like = lower.startswith("#") or (
        lower.startswith("**") and lower.endswith("**")
    )
    if heading_like and (
        "craik contract output" in lower
        or "contract-shaped output" in lower
        or "contract output" in lower
        or "output contract" in lower
    ):
        return "group"
    # A single-marker heading: a bold-wrapped/heading "craik.*" label, or a bare
    # "craik.<token>" line with no surrounding prose (no spaces).
    if (heading_like and "craik." in lower) or (
        lower.startswith("craik.") and " " not in lower
    ):
        return "single"
    return None


def _looks_like_contract_json_line(line: str) -> bool:
    """Whether a trimmed line looks like part of a contract JSON body."""
    if line.startswith(("{", "}", "[", "]")):
        return True
    if line.endswith((",", ":")):
        return True
    lower = line.lower()
    return any(f'"{key}"' in lower for key in _CONTRACT_JSON_KEYS)


def _remove_trailing_contract_separator(output: list[str]) -> None:
    """Pop a trailing ``---``-style rule (and surrounding blanks) before a section.

    A contract section is often preceded by a horizontal rule; once we detect the
    heading we retroactively drop that rule so the kept prose does not end on a
    dangling separator. Mirrors the Rust ``remove_trailing_contract_separator``.
    """
    while output and not output[-1].strip():
        output.pop()
    if output and output[-1].strip() in _CONTRACT_SEPARATORS:
        output.pop()
    while output and not output[-1].strip():
        output.pop()


def _strip_contract_output_sections(text: str) -> str:
    """Strip ``## Craik contract output`` headings and their fenced JSON blocks.

    Line-based port of the Rust ``strip_craik_contract_output_sections``.
    Operates on RAW text WITH newlines intact (it relies on line structure), so
    callers must run it BEFORE any whitespace collapse.
    """
    output: list[str] = []
    skipping_contract = False
    skipping_fence = False
    contract_had_fence = False
    skipping_contract_group = False

    for line in text.splitlines():
        trimmed = line.strip()
        lower = trimmed.lower()

        kind = _contract_heading_kind(lower)
        if kind is not None and not skipping_contract:
            _remove_trailing_contract_separator(output)
            skipping_contract = True
            skipping_fence = False
            contract_had_fence = False
            skipping_contract_group = kind == "group"
            continue

        if skipping_contract:
            if trimmed.startswith("```"):
                if skipping_fence:
                    # Closing fence: a group keeps skipping (more blocks may
                    # follow); a single block ends here.
                    skipping_contract = skipping_contract_group
                    skipping_fence = False
                    contract_had_fence = False
                else:
                    skipping_fence = True
                    contract_had_fence = True
                continue
            if (
                skipping_fence
                or not trimmed
                or _looks_like_contract_json_line(trimmed)
                or (contract_had_fence and _contract_heading_kind(lower) is not None)
            ):
                continue
            # A non-contract, non-blank line ends the section.
            skipping_contract = False
            contract_had_fence = False
            skipping_contract_group = False
            # Drop a lone horizontal rule that immediately followed the section
            # (it was the block's trailing separator, not prose).
            if trimmed in _CONTRACT_SEPARATORS:
                continue

        output.append(line)

    return "\n".join(output)


def _normalize_preserving_structure(text: str) -> str:
    """Trim leading/trailing whitespace and collapse 3+ blank lines to one.

    PRESERVES newlines/markdown -- unlike ``" ".join(text.split())`` it never
    flattens the text to a single paragraph.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    collapsed: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            collapsed.append(line)
        else:
            blank_run += 1
            # Keep at most ONE blank line in a run (3+ -> 1).
            if blank_run <= 1:
                collapsed.append(line)
    return "\n".join(collapsed).strip()


def clean_assistant_text(text: str) -> str:
    """Clean assistant text for operator display + persisted gateway history.

    The fix for the live "wall of text": (1) strip whole ``## Craik contract
    output`` sections (heading + fenced JSON blocks) via the line-based scanner,
    (2) scrub any residual bare envelope-schema-id tokens that appear OUTSIDE a
    detected section (a leakage guard), (3) normalize whitespace WITHOUT
    flattening markdown. The result keeps the prose + Summary the operator wants
    with newlines/lists intact, and drops the contract sections entirely.

    The section scanner (step 1) is heading-gated, so it can NEVER eat a whole
    prose line that merely mentions "contract output" or starts with "craik."
    (the prior over-strip hazard). Step 2 only removes the bare id token, never
    the surrounding sentence.

    MUST run on RAW text with newlines intact (before any whitespace collapse).
    """
    stripped = _strip_contract_output_sections(text)
    for marker in _CONTRACT_ENVELOPE_MARKERS:
        stripped = stripped.replace(marker, "")
    return _normalize_preserving_structure(stripped)


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
