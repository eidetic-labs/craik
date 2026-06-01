"""Real ``GoogleAPI`` adapter: the Gemini ``generateContent`` API surface.

A DELTA of the API-side exemplar :mod:`anthropic_api`. The gate->execute->emit
tool-loop and the receipt allow/deny reconciliation now live once in
:class:`~craik.runtime.backend.adapters.base.APIAdapter`, so this adapter only
declares a ``posture`` and fills the four vendor hooks (``request`` /
``map_response`` / ``execute_tool`` / ``auth_headers``). The base
``direct_tool_loop`` owns the gate->execute->emit orchestration -- including the
receipt event that reflects the side-effects layer's ACTUAL ``allowed`` verdict
(not just ``ctx.decide``) and the ``approval``-denied + denial-receipt emission
for a vetoed tool. ``execute_tool`` returns the standardized
``{"allowed", "receipt_id", "output", "tool_call_id"}`` dict the base consumes.

Task 5.5a: ``run`` is OVERRIDDEN to compose the audited provider core (the live
path); the base ``direct_tool_loop`` remains the fixture-tested direct-HTTP
design. See :meth:`GoogleAPI.run` for the dual-path split.

Composition over reinvention:
  * Request building reuses the provider-runtime types (``ProviderMessage`` /
    ``ProviderTool`` / ``ProviderRuntimeRequest``) and the existing Gemini
    payload builder (``GoogleProviderAdapter.build_payload`` -- the
    ``generateContent`` + ``functionDeclarations`` wire format); the concrete
    HTTP/SDK send is the single overridable ``_send`` seam so tests substitute
    ``request`` wholesale (no network).
  * Response mapping reuses the same candidate/part walk the existing
    ``GoogleProviderAdapter.normalize_response`` performs over ``functionCall``
    parts. Gemini functionCalls carry no vendor call id, so a stable
    ``tool_call_id`` is synthesized (``f"{name}_{index}"``) for multi-tool
    correlation.
  * Tool execution routes through the GATED ``side_effects`` layer
    (``run_shell_command_ref``): authorize -> execute -> signed
    ``CapabilityReceipt`` with redacted output. Execution NEVER bypasses it.

This task builds + unit-tests the adapter in isolation; it is NOT yet wired into
the live ``execute_prompt`` path (cutover is Task 4.7). The google-api id has no
legacy ``execute_prompt`` branch (only the anthropic ids route through one
pre-cutover), so -- like ``GoogleCLI`` and unlike the anthropic exemplar -- this
adapter carries no ``_legacy_run`` bridge.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.adapters.base import (
    APIAdapter,
    ReceiptPosture,
    RunContext,
    optional_str,
    strip_contract_envelopes,
)
from craik.runtime.backend.adapters.vendor_profile import VendorProfile, vendor_profile
from craik.runtime.backend.events import (
    BackendEvent,
    EventSource,
    ReceiptDecidedBy,
    ReceiptMode,
    assistant_text_event,
    tool_event,
)
from craik.runtime.providers.provider_models import (
    ProviderMessage,
    ProviderRuntimeRequest,
    ProviderTool,
)
from craik.runtime.side_effects import (
    CommandExecutor,
    SideEffectResult,
    run_shell_command_ref,
)

if TYPE_CHECKING:
    from craik.contracts.models import CapabilityGrant, PolicyEnvelope
    from craik.runtime.store import LocalStore

# Originating-adapter identifier carried on every emitted event envelope.
_SOURCE: EventSource = "google-api"

# Auth is delegated to the existing google credential source (AI Studio API key,
# or Vertex via google-auth/ADC) resolved by the auth subsystem; the adapter
# NAMES its auth source and does not acquire or store credentials of its own.
_AUTH_SOURCE = "google-credential"

# Receipt posture for API execution: craik authorized AND ran the tool via the
# side-effects layer, hence ``execution="craik"`` (contrast the CLI exemplar's
# ``delegated-observed``). ``mode`` defaults to the non-prompting default until
# the live RunContext threads the real permission mode (Task 4.7 / Phase 5).
_RECEIPT_MODE: ReceiptMode = "default"
_RECEIPT_DECIDED_BY: ReceiptDecidedBy = "operator"

# Default max output tokens for a governed step; small and deterministic.
_DEFAULT_MAX_TOKENS = 1024


@dataclass(frozen=True)
class SideEffectGate:
    """Threaded state the gated ``side_effects`` layer needs to run a tool.

    ``execute_tool`` receives only a ``tool_call``; the authorize+execute+receipt
    path additionally needs a ``store`` (to persist the signed receipt), the
    governing ``policy`` envelope, the operator-approved ``grants``, the
    ``actor`` recorded on the receipt, and the ``executor`` that performs the
    real effect. Holding them on the adapter (injected at construction) keeps
    ``execute_tool``'s signature matching the base hook while still routing every
    effect through the gate. The live wiring lands at cutover (Task 4.7).
    """

    store: LocalStore
    policy: PolicyEnvelope
    grants: list[CapabilityGrant]
    actor: str
    executor: CommandExecutor | None = None


class GoogleAPI(APIAdapter):
    """Adapter that drives the Gemini generateContent tool-loop under craik's veto.

    ``supports_live_gating`` is ``True``: every model-requested tool passes
    through ``ctx.decide`` before execution, and only ``"allow"`` runs the tool
    via the gated side-effects layer.
    """

    vendor = "google"
    surface = "api"
    # API execution posture: craik authorized AND ran the tool via the
    # side-effects layer, hence ``execution="craik"``. The base ``run`` loop
    # stamps this onto every receipt event it emits, so the allowed/gate-deny
    # reconciliation lives once in the base.
    posture = ReceiptPosture(
        source=_SOURCE,
        execution="craik",
        mode=_RECEIPT_MODE,
        decided_by=_RECEIPT_DECIDED_BY,
    )

    def __init__(
        self,
        profile: VendorProfile | None = None,
        *,
        side_effects: SideEffectGate | None = None,
        original_env: dict[str, str] | None = None,
        prompt_source: str = "tui",
    ) -> None:
        super().__init__()
        # ``select_adapter`` injects the profile + side-effect gate at the Task
        # 4.7 cutover; until then default to the canonical google profile.
        self.profile: VendorProfile = profile or vendor_profile("google")
        self._side_effects = side_effects
        # The ORIGINAL env (possibly None) the provider core needs -- threaded
        # separately from ``RunContext.env`` (coerced to ``{}``), like the legacy
        # provider path. 5.7 injects this; tests set it directly.
        self.original_env: dict[str, str] | None = original_env
        # Operator ``PromptSource`` recorded on the created task by the provider
        # core; 5.7 injects the real source, defaulting to ``"tui"`` until then.
        self.prompt_source: str = prompt_source
        # The governed function-tool the model may call. Registered here so the
        # base ``function_tools`` (which strips hosted tools) sends exactly this.
        self.register_tool(
            {
                "type": "function",
                "name": "run_shell_command",
                "description": "Run a governed shell command reference.",
            }
        )

    def supports_live_gating(self) -> bool:
        return True

    def auth_source(self) -> str:
        """Name the delegated google credential profile.

        Metadata only: the adapter records auth provenance for the seam and does
        not acquire or persist credentials. The same google credential source
        (AI Studio API key, or Vertex via google-auth/ADC) the rest of craik
        resolves.
        """
        return _AUTH_SOURCE

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """Compose the audited provider core, yielding the NEW TYPED event sequence.

        OVERRIDES the base ``APIAdapter.run`` (the direct-HTTP tool-loop): the
        live-today provider path runs + persists through the SAME
        ``ProviderBackedRunExecutor`` all families share, via
        ``audited_core.run_provider_typed``, then derives typed events and closes
        the store once. See ``AnthropicAPI.run`` for the dual-path split (base
        ``direct_tool_loop`` stays the fixture-tested direct-HTTP design) and the
        vendor/provider_family alignment note. NOT wired into ``execute_prompt``
        (Task 5.7).
        """
        from craik.runtime.backend.adapters.audited_core import run_provider_typed

        yield from run_provider_typed(
            prompt=ctx.prompt,
            env=self.original_env,
            source=_SOURCE,
            provider_source=self.prompt_source,  # type: ignore[arg-type]
        )

    # --- abstract hooks -----------------------------------------------------

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        env: dict[str, str],
    ) -> Any:
        """Build + send one Gemini ``generateContent`` request.

        Composes the provider-runtime request types and the existing Gemini
        payload builder rather than hand-rolling HTTP; the concrete send is the
        overridable ``_send`` seam (the one place real network would happen).
        Unit tests substitute this method wholesale with a fake returning the
        recorded raw ``generateContent`` response.
        """
        runtime_request = self._build_runtime_request(messages, tools)
        return self._send(runtime_request, env=env)

    def _build_runtime_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderRuntimeRequest:
        provider_messages = [
            ProviderMessage(role="user", content=_message_text(message)) for message in messages
        ]
        provider_tools = [
            ProviderTool(
                name=str(spec.get("name") or "tool"),
                description=str(spec.get("description") or ""),
                input_schema=_tool_input_schema(spec),
            )
            for spec in tools
        ]
        return ProviderRuntimeRequest(
            messages=provider_messages,
            tools=provider_tools,
            max_output_tokens=_DEFAULT_MAX_TOKENS,
        )

    def _send(self, request: ProviderRuntimeRequest, *, env: dict[str, str]) -> Any:
        """Perform the real ``generateContent`` API call.

        Composes the existing Gemini payload builder to produce the
        ``generateContent`` wire request (``functionDeclarations`` from the
        governed tools), then hands it to the live transport. Left unimplemented
        in this task: the live transport bridge lands with the cutover (Task
        4.7). Tests override ``request`` so this is never reached; calling it
        before the cutover is a programming error.
        """
        raise NotImplementedError(
            "GoogleAPI._send is wired to the live generateContent transport in Task 4.7"
        )

    def map_response(
        self,
        response: Any,
    ) -> tuple[list[BackendEvent], list[dict[str, Any]]]:
        """Map a raw ``generateContent`` response to ``(events, tool_calls)``.

        Walks the candidate parts exactly as the existing Gemini provider
        normalization does: ``text`` parts -> a coalesced ``assistant_text``
        (contract envelopes stripped); each ``functionCall`` part -> a tool_call
        dict carrying ``id`` / ``name`` / ``args`` plus a ``tool.used`` event.
        Gemini functionCalls carry no vendor call id, so a stable ``id`` is
        synthesized (``f"{name}_{index}"``) for multi-tool correlation.
        """
        events: list[BackendEvent] = []
        tool_calls: list[dict[str, Any]] = []
        text_parts: list[str] = []
        index = 0
        for part in _candidate_parts(response):
            if "text" in part:
                text_parts.append(str(part.get("text") or ""))
            function_call = part.get("functionCall")
            if isinstance(function_call, dict):
                name = str(function_call.get("name") or "tool")
                tool_call = {
                    "id": _tool_call_id(function_call, name, index),
                    "name": name,
                    "args": function_call.get("args", {}),
                }
                index += 1
                tool_calls.append(tool_call)
                events.append(
                    tool_event(
                        tool=name,
                        source=_SOURCE,
                        command=optional_str(_command_from_args(tool_call["args"])),
                    )
                )
        text = strip_contract_envelopes("".join(text_parts))
        if text:
            events.insert(0, assistant_text_event(text=text, source=_SOURCE))
        return events, tool_calls

    def execute_tool(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Execute one ALLOWED tool VIA the gated side-effects layer.

        Routes the tool through ``run_shell_command_ref`` (authorize -> execute
        -> signed ``CapabilityReceipt`` with redacted output). Returns the
        standardized ``{"allowed", "receipt_id", "output", "tool_call_id"}`` dict
        the base ``run`` loop consumes. ``allowed`` is the gate's ACTUAL verdict
        and MAY be ``False`` even when ``ctx.decide`` said allow (the gate's
        ``check_shell_grant`` vetoed); on that disagreement ``receipt.id`` is the
        persisted DENIAL receipt and the base emits a ``deny`` receipt event.
        Execution NEVER bypasses the gate.
        """
        gate = self._require_gate()
        command_ref = _command_from_args(tool_call.get("args", {}))
        effect: SideEffectResult = run_shell_command_ref(
            store=gate.store,
            policy=gate.policy,
            grants=gate.grants,
            actor=gate.actor,
            command_ref=command_ref,
            executor=gate.executor,
        )
        return {
            "tool_call_id": tool_call.get("id"),
            "receipt_id": effect.receipt.id,
            "allowed": effect.allowed,
            "output": effect.output,
        }

    def auth_headers(self, env: dict[str, str]) -> dict[str, str]:
        """Return Gemini generateContent auth headers from the google credential.

        References the existing google credential mechanism via the env-resolved
        key (the ``x-goog-api-key`` header the auth CLI bridge already issues for
        the google family); it implements no new auth flow. Absent a key
        (pre-cutover / tests), returns no auth header.
        """
        headers: dict[str, str] = {}
        resolved = env.get("GOOGLE_API_KEY") or env.get("GEMINI_API_KEY")
        if resolved:
            headers["x-goog-api-key"] = resolved
        return headers

    def _require_gate(self) -> SideEffectGate:
        if self._side_effects is None:
            raise NotImplementedError(
                "GoogleAPI.execute_tool requires an injected SideEffectGate "
                "(wired live at the Task 4.7 cutover)"
            )
        return self._side_effects


def _candidate_parts(response: Any) -> list[dict[str, Any]]:
    """Yield the content parts across all candidates of a generateContent body.

    Mirrors ``GoogleProviderAdapter.normalize_response``'s candidate/part walk.
    """
    parts: list[dict[str, Any]] = []
    if not isinstance(response, dict):
        return parts
    candidates = response.get("candidates")
    if not isinstance(candidates, list):
        return parts
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []):
            if isinstance(part, dict):
                parts.append(part)
    return parts


def _tool_call_id(function_call: dict[str, Any], name: str, index: int) -> str:
    """Return the functionCall id, synthesizing a stable one when absent.

    Gemini ``functionCall`` parts may carry no vendor call id; a deterministic
    ``f"{name}_{index}"`` keeps multi-tool correlation working across the loop.
    """
    vendor_id = optional_str(function_call.get("id"))
    return vendor_id or f"{name}_{index}"


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    return content if isinstance(content, str) else str(content)


def _tool_input_schema(spec: dict[str, Any]) -> dict[str, Any]:
    schema = spec.get("input_schema")
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


def _command_from_args(args: Any) -> str:
    """Extract the command reference from a functionCall ``args`` payload."""
    if isinstance(args, dict):
        command = args.get("command")
        if isinstance(command, str) and command.strip():
            return command
    return str(args)


__all__ = ["GoogleAPI", "SideEffectGate"]
