"""Real ``AnthropicAPI`` adapter: the API-side Phase-4 exemplar.

This is the canonical API adapter pattern that ``GoogleAPI`` (Task 4.4) and
``OpenAIAPI`` (Task 4.5) follow:

    gate (``ctx.decide``) -> execute-via-side-effects -> signed receipt
    (``execution="craik"`` -- craik ran the tool itself).

It subclasses :class:`~craik.runtime.backend.adapters.base.APIAdapter` and fills
the four abstract hooks (``request`` / ``map_response`` / ``execute_tool`` /
``auth_headers``) plus declares a ``posture``. The base ``direct_tool_loop``
owns the gate->execute->emit orchestration -- including the receipt event that
reflects the side-effects layer's ACTUAL ``allowed`` verdict (not just
``ctx.decide``) and the ``approval``-denied + denial-receipt emission for a
vetoed tool -- so all three API adapters share one correct loop. ``execute_tool``
returns the standardized
``{"allowed", "receipt_id", "output", "tool_call_id"}`` dict the base consumes.

Task 5.5a: ``run`` is OVERRIDDEN to compose the audited provider core (the live
path); the base ``direct_tool_loop`` remains the fixture-tested direct-HTTP
design. See :meth:`AnthropicAPI.run` for the dual-path split.

Composition over reinvention:
  * Request building reuses the provider-runtime types (``ProviderMessage`` /
    ``ProviderTool`` / ``ProviderRuntimeRequest``) and the existing Anthropic
    payload builder; the concrete HTTP/SDK send is the single overridable
    ``_send`` seam so tests substitute ``request`` wholesale (no network).
  * Response mapping reuses the same content-block walk the existing
    ``AnthropicProviderAdapter.normalize_response`` performs.
  * Tool execution routes through the GATED ``side_effects`` layer
    (``run_shell_command_ref``): authorize -> execute -> signed
    ``CapabilityReceipt`` with redacted output. Execution NEVER bypasses it.

This task builds + unit-tests the adapter in isolation; it is NOT yet wired into
the live ``execute_prompt`` path (cutover is Task 4.7). The ``_legacy_run``
bridge keeps the live provider path byte-identical until then.
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
    from craik.runtime.backend.session import BackendPromptResult
    from craik.runtime.store import LocalStore

# Originating-adapter identifier carried on every emitted event envelope.
_SOURCE: EventSource = "anthropic-api"

# Auth is the craik API-key credential profile (the anthropic api-key namespace
# resolved by the auth subsystem); the adapter NAMES its auth source and does
# not acquire or store credentials of its own.
_AUTH_SOURCE = "anthropic-api-key"

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


class AnthropicAPI(APIAdapter):
    """Adapter that drives the Anthropic Messages tool-loop under craik's veto.

    ``supports_live_gating`` is ``True``: every model-requested tool passes
    through ``ctx.decide`` before execution, and only ``"allow"`` runs the tool
    via the gated side-effects layer.
    """

    vendor = "anthropic"
    surface = "api"
    # API execution posture: craik authorized AND ran the tool via the
    # side-effects layer, hence ``execution="craik"`` (contrast the CLI
    # exemplar's ``delegated-observed``). The base ``run`` loop stamps this onto
    # every receipt event it emits, so the allowed/gate-deny reconciliation lives
    # once in the base.
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
        # 4.7 cutover; until then default to the canonical anthropic profile.
        self.profile: VendorProfile = profile or vendor_profile("anthropic")
        self._side_effects = side_effects
        # The ORIGINAL env (possibly None) the provider core needs -- threaded
        # separately from ``RunContext.env`` (coerced to ``{}``), exactly as the
        # legacy provider path threads ``env=`` separately. ``select_adapter``
        # injects this at the Task 5.7 cutover; tests set it directly.
        self.original_env: dict[str, str] | None = original_env
        # Operator ``PromptSource`` recorded on the created task by the provider
        # core (legacy threaded it via ``_legacy_run(source=...)``); 5.7 injects
        # the real source, defaulting to ``"tui"`` until then.
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
        """Name the craik anthropic api-key credential profile.

        Metadata only: the adapter records auth provenance for the seam and does
        not acquire or persist credentials.
        """
        return _AUTH_SOURCE

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """Compose the audited provider core, yielding the NEW TYPED event sequence.

        This OVERRIDES the base ``APIAdapter.run`` (the direct-HTTP tool-loop):
        the live-today provider path runs + persists through
        ``ProviderBackedRunExecutor`` -- the SAME machinery all provider families
        share -- via ``audited_core.run_provider_typed``. ``run()`` then derives
        the typed events from the ``ProviderCoreResult`` and closes the core's
        store exactly once (leak-free), mirroring
        ``legacy_runs._legacy_provider_run``. It is the typed counterpart of the
        legacy provider emission layer.

        Dual-path: the base ``direct_tool_loop`` (gate->request->map_response->
        execute_tool + ``SideEffectGate``) remains the fixture-tested direct-HTTP
        design (the Phase-4 ``*API`` tests drive it via ``direct_tool_loop``); it
        is NOT the live path. Only ONE path runs per call -- this ``run`` composes
        the core; it never also runs the base loop.

        Vendor/provider_family alignment: ``run_provider_core`` resolves
        ``provider_id`` / ``provider_family`` from the active model/env (as the
        legacy provider path did). This adapter stamps its OWN vendor token
        (``anthropic-api``) on emitted events, and ``run_provider_typed`` GUARDS
        that the vendor agrees with the resolved ``provider_family`` -- on
        mismatch it refuses to emit (raising), rather than write a wrong-vendor
        audit record. ``execute_prompt`` (Task 5.7) selects the adapter matching
        the active provider so the guard holds. NOT wired into ``execute_prompt``
        here (Task 5.7).
        """
        from craik.runtime.backend.adapters.audited_core import run_provider_typed

        yield from run_provider_typed(
            prompt=ctx.prompt,
            # The ORIGINAL env (possibly None), threaded like the legacy path.
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
        """Build + send one Anthropic Messages request.

        Composes the provider-runtime request types rather than hand-rolling
        HTTP; the concrete send is the overridable ``_send`` seam (the one place
        real network would happen). Unit tests substitute this method wholesale
        with a fake returning the recorded raw Messages response.
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
        """Perform the real Messages API call.

        Left unimplemented in this task: the live transport bridge lands with the
        cutover (Task 4.7). Tests override ``request`` so this is never reached;
        calling it before the cutover is a programming error.
        """
        raise NotImplementedError(
            "AnthropicAPI._send is wired to the live Messages transport in Task 4.7"
        )

    def map_response(
        self,
        response: Any,
    ) -> tuple[list[BackendEvent], list[dict[str, Any]]]:
        """Map a raw Messages response to ``(events, tool_calls)``.

        Walks the ``content`` blocks exactly as the existing Anthropic provider
        normalization does: ``text`` blocks -> a coalesced ``assistant_text``
        (contract envelopes stripped); ``tool_use`` blocks -> a tool_call dict
        carrying ``id`` / ``name`` / ``input`` plus a ``tool.used`` event.
        """
        events: list[BackendEvent] = []
        tool_calls: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for block in _content_blocks(response):
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(str(block.get("text", "")))
            elif block_type == "tool_use":
                tool_call = {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                }
                tool_calls.append(tool_call)
                events.append(
                    tool_event(
                        tool=str(tool_call["name"] or "tool"),
                        source=_SOURCE,
                        command=optional_str(_command_from_input(tool_call["input"])),
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
        command_ref = _command_from_input(tool_call.get("input", {}))
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
        """Return Anthropic Messages auth headers from the craik api-key profile.

        References the existing api-key credential mechanism via the env-resolved
        key; it implements no new auth flow. Absent a key (pre-cutover / tests),
        returns the static, non-secret protocol headers only.
        """
        headers = {"anthropic-version": "2023-06-01"}
        resolved = env.get("ANTHROPIC_API_KEY")
        if resolved:
            headers["x-api-key"] = resolved
        return headers

    def _require_gate(self) -> SideEffectGate:
        if self._side_effects is None:
            raise NotImplementedError(
                "AnthropicAPI.execute_tool requires an injected SideEffectGate "
                "(wired live at the Task 4.7 cutover)"
            )
        return self._side_effects

    def _legacy_run(
        self,
        ctx: RunContext,
        *,
        events: list[BackendEvent],
        source: str,
        env: dict[str, str] | None,
    ) -> BackendPromptResult:
        """Bridge to the legacy provider path (pre-cutover seam).

        ``execute_prompt`` still drives the live provider path through this
        bridge until the Task 4.7 cutover replaces it with ``run``; keeping it
        here preserves byte-identical behavior. ``env`` is the ORIGINAL value
        (possibly None), threaded separately from ``ctx.env``.
        """
        from craik.runtime.backend.adapters.legacy_runs import _legacy_provider_run

        return _legacy_provider_run(
            prompt=ctx.prompt,
            env=env,
            emit=ctx.emit,
            events=events,
            source=source,  # type: ignore[arg-type]
        )


def _content_blocks(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        blocks = response.get("content")
        if isinstance(blocks, list):
            return [block for block in blocks if isinstance(block, dict)]
    return []


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    return content if isinstance(content, str) else str(content)


def _tool_input_schema(spec: dict[str, Any]) -> dict[str, Any]:
    schema = spec.get("input_schema")
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


def _command_from_input(tool_input: Any) -> str:
    """Extract the command reference from a tool_use ``input`` payload."""
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str) and command.strip():
            return command
    return str(tool_input)


__all__ = ["AnthropicAPI", "SideEffectGate"]
