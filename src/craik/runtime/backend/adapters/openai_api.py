"""Real ``OpenAIAPI`` adapter: the OpenAI Responses API surface.

A DELTA of the API-side exemplars :mod:`anthropic_api` / :mod:`google_api`. The
gate->execute->emit tool-loop and the receipt allow/deny reconciliation live once
in :class:`~craik.runtime.backend.adapters.base.APIAdapter`, so this adapter only
declares a ``posture`` and fills the four vendor hooks (``request`` /
``map_response`` / ``execute_tool`` / ``auth_headers``). The base
``direct_tool_loop`` owns the gate->execute->emit orchestration -- including the
receipt event that reflects the side-effects layer's ACTUAL ``allowed`` verdict
(not just ``ctx.decide``) and the ``approval``-denied + denial-receipt emission
for a vetoed tool. ``execute_tool`` returns the standardized
``{"allowed", "receipt_id", "output", "tool_call_id"}`` dict the base consumes.

Task 5.5a: ``run`` is OVERRIDDEN to compose the audited provider core (the live
path); the base ``direct_tool_loop`` remains the fixture-tested direct-HTTP
design. See :meth:`OpenAIAPI.run` for the dual-path split.

Composition over reinvention:
  * Request building reuses the provider-runtime types (``ProviderMessage`` /
    ``ProviderTool`` / ``ProviderRuntimeRequest``); the concrete HTTP/SDK send is
    the single overridable ``_send`` seam so tests substitute ``request``
    wholesale (no network). The wire path (``/v1/responses`` vs
    ``/v1/chat/completions``) the seam targets is chosen by ``_wire_path`` so the
    fallback is an explicit, selected branch -- not a half-wired stub.
  * Response mapping reuses the same walks the existing OpenAI provider
    normalization performs: the Responses ``output`` walk
    (``OpenAIProviderAdapter.normalize_response`` -- ``function_call`` items carry
    a vendor ``call_id`` / ``id``, ``output_text`` content blocks carry text) and
    the Chat Completions ``choices[].message`` walk
    (``ChatCompletionsProviderAdapter.normalize_response`` -- ``tool_calls`` carry
    a vendor ``id`` and ``function.arguments``).
  * Tool execution routes through the GATED ``side_effects`` layer
    (``run_shell_command_ref``): authorize -> execute -> signed
    ``CapabilityReceipt`` with redacted output. Execution NEVER bypasses it.

Fallback posture: this adapter implements the Responses path as primary AND a
Chat Completions fallback as a REAL, tested code path selected at construction by
``use_chat_completions``; both share the inherited gate->execute->emit loop.

This adapter's typed ``run()`` is now the DEFAULT live ``execute_prompt`` path.
The openai-api id has no legacy ``execute_prompt`` branch (only the anthropic
ids route through one), so -- like ``GoogleAPI`` and unlike the anthropic
exemplar -- this adapter carries no ``_legacy_run`` bridge and no
``CRAIK_BACKEND_LEGACY_RUN`` fallback.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.adapters.assistant_text import clean_assistant_text
from craik.runtime.backend.adapters.base import (
    APIAdapter,
    ReceiptPosture,
    RunContext,
    optional_str,
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
_SOURCE: EventSource = "openai-api"

# Auth is delegated to the existing OpenAI credential source (the api-key
# namespace resolved by the auth subsystem, or the Azure OpenAI endpoint/key
# variant when those env vars are set); the adapter NAMES its auth source and
# does not acquire or store credentials of its own.
_AUTH_SOURCE = "openai-api-key"

# Receipt posture for API execution: craik authorized AND ran the tool via the
# side-effects layer, hence ``execution="craik"`` (contrast the CLI exemplar's
# ``delegated-observed``). ``mode`` defaults to the non-prompting default until
# the live RunContext threads the real permission mode (Task 4.7 / Phase 5).
_RECEIPT_MODE: ReceiptMode = "default"
_RECEIPT_DECIDED_BY: ReceiptDecidedBy = "operator"

# Default max output tokens for a governed step; small and deterministic.
_DEFAULT_MAX_TOKENS = 1024

# Wire paths the ``_send`` seam targets, selected by ``use_chat_completions``.
_RESPONSES_PATH = "/v1/responses"
_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


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


class OpenAIAPI(APIAdapter):
    """Adapter that drives the OpenAI Responses tool-loop under craik's veto.

    ``supports_live_gating`` is ``True``: every model-requested tool passes
    through ``ctx.decide`` before execution, and only ``"allow"`` runs the tool
    via the gated side-effects layer. The primary surface is the Responses API;
    ``use_chat_completions=True`` selects the Chat Completions fallback as a real,
    governed path that shares the inherited loop.
    """

    vendor = "openai"
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
        use_chat_completions: bool = False,
        original_env: dict[str, str] | None = None,
        prompt_source: str = "tui",
    ) -> None:
        super().__init__()
        # ``select_adapter`` injects the profile + side-effect gate at the Task
        # 4.7 cutover; until then default to the canonical openai profile.
        self.profile: VendorProfile = profile or vendor_profile("openai")
        self._side_effects = side_effects
        # The ORIGINAL env (possibly None) the provider core needs -- threaded
        # separately from ``RunContext.env`` (coerced to ``{}``), like the legacy
        # provider path. 5.7 injects this; tests set it directly.
        self.original_env: dict[str, str] | None = original_env
        # Operator ``PromptSource`` recorded on the created task by the provider
        # core; 5.7 injects the real source, defaulting to ``"tui"`` until then.
        self.prompt_source: str = prompt_source
        # Payload-capture seam (Task 5.7): the generator-shaped run() stashes the
        # audited core payload here for ``execute_prompt`` to read.
        self.last_payload: dict[str, object] | None = None
        # Primary surface is the Responses API; the Chat Completions fallback is a
        # real, selectable branch (request building + response parsing) that
        # shares the inherited gate->execute->emit loop.
        self._use_chat_completions = use_chat_completions
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
        """Name the delegated OpenAI credential profile.

        Metadata only: the adapter records auth provenance for the seam and does
        not acquire or persist credentials. The same OpenAI credential source
        (api key, or the Azure OpenAI endpoint/key variant) the rest of craik
        resolves.
        """
        return _AUTH_SOURCE

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """Compose the audited provider core, yielding the NEW TYPED event sequence.

        OVERRIDES the base ``APIAdapter.run`` (the direct-HTTP tool-loop): the
        live-today provider path runs + persists through the SAME
        ``ProviderBackedRunExecutor`` all families share, via the shared
        ``audited_core.provider_api_run`` wiring (the identical body
        ``AnthropicAPI`` / ``GoogleAPI`` also compose): it derives typed events,
        captures the audited payload onto ``self.last_payload``, and closes the
        store once. See ``AnthropicAPI.run`` for the dual-path split (base
        ``direct_tool_loop`` -- with its Responses/Chat-Completions branches --
        stays the fixture-tested direct-HTTP design) and the vendor/provider_family
        alignment note. This ``run()`` IS the live ``execute_prompt`` path
        (openai-api has no legacy branch / no ``CRAIK_BACKEND_LEGACY_RUN``
        fallback).
        """
        from craik.runtime.backend.adapters.audited_core import provider_api_run

        return provider_api_run(self, ctx)

    # --- abstract hooks -----------------------------------------------------

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        env: dict[str, str],
    ) -> Any:
        """Build + send one OpenAI request (Responses primary / Chat fallback).

        Composes the provider-runtime request types rather than hand-rolling
        HTTP; the concrete send is the overridable ``_send`` seam (the one place
        real network would happen), and ``_wire_path`` selects the Responses vs
        Chat Completions endpoint. Unit tests substitute this method wholesale
        with a fake returning the recorded raw response.
        """
        runtime_request = self._build_runtime_request(messages, tools)
        return self._send(runtime_request, env=env)

    def _wire_path(self) -> str:
        """Return the wire endpoint path for the selected OpenAI surface."""
        return _CHAT_COMPLETIONS_PATH if self._use_chat_completions else _RESPONSES_PATH

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
        """Perform the real OpenAI API call against the selected wire path.

        Left unimplemented in this task: the live transport bridge lands with the
        cutover (Task 4.7). Tests override ``request`` so this is never reached;
        calling it before the cutover is a programming error.
        """
        raise NotImplementedError(
            f"OpenAIAPI._send is wired to the live {self._wire_path()} transport in Task 4.7"
        )

    def map_response(
        self,
        response: Any,
    ) -> tuple[list[BackendEvent], list[dict[str, Any]]]:
        """Map a raw response to ``(events, tool_calls)``.

        Dispatches on the selected surface: the Responses ``output`` walk or the
        Chat Completions ``choices[].message`` walk. Either way assistant text is
        coalesced into a single ``assistant_text`` (contract envelopes stripped)
        and each function/tool call yields a tool_call dict carrying the vendor
        call id plus a ``tool.used`` event.
        """
        if self._use_chat_completions:
            return self._map_chat_completions(response)
        return self._map_responses(response)

    def _map_responses(
        self,
        response: Any,
    ) -> tuple[list[BackendEvent], list[dict[str, Any]]]:
        """Walk a Responses ``output`` list (mirrors OpenAIProviderAdapter)."""
        events: list[BackendEvent] = []
        tool_calls: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for item in _response_output(response):
            if item.get("type") == "function_call":
                # Responses function calls DO carry a vendor call id; prefer
                # ``call_id`` (the id threaded back on tool results), then ``id``.
                name = str(item.get("name") or "tool")
                arguments = _decode_arguments(item.get("arguments"))
                tool_call = {
                    "id": optional_str(item.get("call_id")) or optional_str(item.get("id")) or name,
                    "name": name,
                    "arguments": arguments,
                }
                tool_calls.append(tool_call)
                events.append(
                    tool_event(
                        tool=name,
                        source=_SOURCE,
                        command=optional_str(_command_from_arguments(arguments)),
                    )
                )
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text_parts.append(str(content.get("text") or ""))
        text = clean_assistant_text(
            str(_text_field(response, "output_text")) + "".join(text_parts)
        )
        if text:
            events.insert(0, assistant_text_event(text=text, source=_SOURCE))
        return events, tool_calls

    def _map_chat_completions(
        self,
        response: Any,
    ) -> tuple[list[BackendEvent], list[dict[str, Any]]]:
        """Walk a Chat Completions ``choices[].message`` (the fallback path)."""
        events: list[BackendEvent] = []
        tool_calls: list[dict[str, Any]] = []
        message = _chat_message(response)
        for index, raw in enumerate(_chat_tool_calls(message)):
            raw_function = raw.get("function")
            function: dict[str, Any] = raw_function if isinstance(raw_function, dict) else {}
            name = str(function.get("name") or "tool")
            arguments = _decode_arguments(function.get("arguments"))
            tool_call = {
                "id": optional_str(raw.get("id")) or f"{name}_{index}",
                "name": name,
                "arguments": arguments,
            }
            tool_calls.append(tool_call)
            events.append(
                tool_event(
                    tool=name,
                    source=_SOURCE,
                    command=optional_str(_command_from_arguments(arguments)),
                )
            )
        text = clean_assistant_text(str(message.get("content") or ""))
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
        command_ref = _command_from_arguments(tool_call.get("arguments", {}))
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
        """Return OpenAI auth headers from the env-resolved credential.

        References the existing api-key credential mechanism; it implements no new
        auth flow. When the Azure OpenAI endpoint/key env variant is set
        (``AZURE_OPENAI_ENDPOINT`` + ``AZURE_OPENAI_API_KEY``), emits the
        Azure-style ``api-key`` header instead of the bearer token. Absent any
        key (pre-cutover / tests), returns no auth header.
        """
        headers: dict[str, str] = {}
        azure_endpoint = env.get("AZURE_OPENAI_ENDPOINT")
        azure_key = env.get("AZURE_OPENAI_API_KEY")
        if azure_endpoint and azure_key:
            # Azure OpenAI authenticates with an ``api-key`` header against the
            # deployment endpoint rather than a bearer token.
            headers["api-key"] = azure_key
            return headers
        resolved = env.get("OPENAI_API_KEY")
        if resolved:
            headers["Authorization"] = f"Bearer {resolved}"
        return headers

    def _require_gate(self) -> SideEffectGate:
        if self._side_effects is None:
            raise NotImplementedError(
                "OpenAIAPI.execute_tool requires an injected SideEffectGate "
                "(wired live at the Task 4.7 cutover)"
            )
        return self._side_effects


def _response_output(response: Any) -> list[dict[str, Any]]:
    """Yield the ``output`` items of a Responses body (mirrors the provider)."""
    if not isinstance(response, dict):
        return []
    output = response.get("output")
    if not isinstance(output, list):
        return []
    return [item for item in output if isinstance(item, dict)]


def _text_field(response: Any, key: str) -> str:
    if isinstance(response, dict):
        value = response.get(key)
        if isinstance(value, str):
            return value
    return ""


def _chat_message(response: Any) -> dict[str, Any]:
    """Return the first Chat Completions ``choices[].message`` dict, or empty."""
    if not isinstance(response, dict):
        return {}
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            return message
    return {}


def _chat_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return [call for call in tool_calls if isinstance(call, dict)]


def _decode_arguments(value: Any) -> dict[str, Any]:
    """Coerce a function-call ``arguments`` payload to a dict.

    OpenAI serializes call arguments as a JSON string; tolerate an already-parsed
    dict (and any other shape -> empty dict).
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    return content if isinstance(content, str) else str(content)


def _tool_input_schema(spec: dict[str, Any]) -> dict[str, Any]:
    schema = spec.get("input_schema")
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


def _command_from_arguments(arguments: Any) -> str:
    """Extract the command reference from a function-call ``arguments`` payload."""
    if isinstance(arguments, dict):
        command = arguments.get("command")
        if isinstance(command, str) and command.strip():
            return command
    return str(arguments)


__all__ = ["OpenAIAPI", "SideEffectGate"]
