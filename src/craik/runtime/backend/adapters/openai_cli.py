"""Real ``OpenAICLI`` adapter: the OBSERVE-ONLY OpenAI CLI surface.

A DELTA following the Phase-4 CLI exemplars :mod:`anthropic_cli` /
:mod:`google_cli`. It subclasses
:class:`~craik.runtime.backend.adapters.base.CLIAdapter` and fills the three
abstract hooks (``build_command`` / ``spawn`` / ``map_native_event``) plus an
overridden ``parse_stream`` that coalesces cumulative assistant-text snapshots.
The base does the heavy lifting; this module owns only the ``codex exec --json``
``thread`` / ``turn`` / ``item.*`` vocabulary -> canonical-event translation.

OBSERVE-ONLY -- the one material divergence from the gating CLIs
========================================================================
This surface CANNOT live-gate. Per ``docs/adapters/vendor-capabilities.md``
(§ OpenAI, ``codex`` pinned 0.135.0, last re-smoke 2026-05-30) and
``docs/adapters/flows/openai-cli.md``: Codex's ``PreToolUse`` /
``PermissionRequest`` hook **did NOT fire** for the shell tool under
``codex exec`` (v0.135.0). The negative was confirmed across a controlled
surface -- project-local AND user-level config, ``--full-auto``,
``approval_policy="untrusted"``, isolated ``CODEX_HOME`` -- and with BOTH a
``.*`` wildcard matcher AND an explicit ``Bash`` matcher. It is therefore NOT a
config error or a matcher problem; the root cause is documented by OpenAI: the
``unified_exec`` shell path's hook interception is incomplete -- "a guardrail
rather than a complete enforcement boundary."

Consequence (verified fact, NOT a stub): ``supports_live_gating`` is ``False``
and the adapter REFUSES to gate -- ``require_live_gating`` raises
:class:`LiveGatingUnsupported`, and ``run`` raises the same when a caller asks
for operator approval. **Live governance over OpenAI MUST go through the
``openai-api`` surface** (caller-executed custom function tools form a complete
enforcement boundary). Re-smoke on each Codex upgrade; this may improve as
``unified_exec`` interception matures.

Observe-only attribution: because the hook never fires, craik did NOT authorize
the call pre-execution. The receipts this adapter emits attest OBSERVATION only,
not an enforced authorization decision -- so ``decided_by`` is ``"bypass"`` (the
documented ungoverned audit flag), NEVER the ``"operator"`` value the gating
CLIs stamp. ``execution="delegated-observed"``: the codex CLI ran the side
effect; craik observed and recorded the reported result.

This task builds + unit-tests the adapter in isolation; it is NOT yet wired into
the live ``execute_prompt`` path (cutover is Task 4.7). The openai-cli id has no
legacy ``execute_prompt`` branch (only the anthropic ids route through one
pre-cutover), so -- like ``GoogleCLI`` and unlike the anthropic exemplar -- this
adapter carries no ``_legacy_run`` bridge.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable, Iterator
from typing import Any

from craik.runtime.backend.adapters.base import (
    CLIAdapter,
    RunContext,
    optional_str,
    strip_contract_envelopes,
)
from craik.runtime.backend.adapters.vendor_profile import VendorProfile, vendor_profile
from craik.runtime.backend.events import (
    BackendEvent,
    Coalescer,
    EventSource,
    ReceiptDecidedBy,
    receipt_event,
    tool_event,
)

# Originating-adapter identifier carried on every emitted event envelope.
_SOURCE: EventSource = "openai-cli"

# Auth is delegated to the existing OpenAI api-key credential source resolved by
# the auth subsystem; the adapter NAMES its auth source only and acquires no
# credentials. There is no sanctioned headless subscription token for the codex
# CLI (subscription headless use is unsupported / a gray-zone path), so this
# surface is api-key only -- matching the ``openai-api`` auth-source naming.
_AUTH_SOURCE = "openai-api-key"

# Observe-only governance attribution. Because the codex CLI's pre-tool hook
# does not fire (see module docstring + vendor-capabilities.md), craik did NOT
# authorize the call pre-execution. ``"bypass"`` is the documented ungoverned
# audit flag -- the receipt honestly attests OBSERVATION, never the ``operator``
# authorization the gating CLIs (AnthropicCLI / GoogleCLI) record.
_OBSERVE_ONLY_DECIDED_BY: ReceiptDecidedBy = "bypass"


class LiveGatingUnsupported(RuntimeError):
    """Raised when an observe-only adapter is asked to live-gate a tool call.

    The ``openai-cli`` surface cannot enforce a pre-execution veto (the codex
    CLI's hook does not fire for the shell tool, verified negative). Callers
    needing live governance over OpenAI must use the ``openai-api`` surface.
    """


class OpenAICLI(CLIAdapter):
    """Adapter that runs the codex CLI and maps its stream to OBSERVE events.

    ``supports_live_gating`` is ``False``: this surface cannot gate tool calls
    before they execute (the codex CLI's pre-tool hook does not fire for the
    shell tool -- see ``docs/adapters/vendor-capabilities.md``). It REFUSES to
    gate via ``require_live_gating`` / ``run``, pointing operators to the
    ``openai-api`` surface for live governance.
    """

    vendor = "openai"
    surface = "cli"

    def __init__(self, profile: VendorProfile | None = None) -> None:
        # ``select_adapter`` will inject the profile at construction in Task 4.7;
        # until then default to the canonical openai profile.
        self.profile: VendorProfile = profile or vendor_profile("openai")
        # Per-run coalescer for cumulative assistant-text snapshots. Reset at
        # the start of every ``parse_stream`` so runs never bleed together.
        self._coalescer = Coalescer()

    def supports_live_gating(self) -> bool:
        # VERIFIED observe-only: the codex CLI's pre-tool hook does not fire for
        # the shell tool (vendor-capabilities.md § OpenAI). Not a stub default.
        return False

    def require_live_gating(self) -> None:
        """Refuse to gate: raise :class:`LiveGatingUnsupported`.

        The observe-only guard. A caller that reaches a gate/decision path on
        this adapter is misrouted -- live governance over OpenAI must go through
        the ``openai-api`` surface (caller-executed function tools form a
        complete enforcement boundary). The message names that surface so the
        operator remediation is explicit.
        """
        raise LiveGatingUnsupported(
            "openai-cli is observe-only and cannot live-gate tool calls "
            "(the codex CLI pre-tool hook does not fire for the shell tool); "
            "route live governance over OpenAI through the openai-api surface."
        )

    def auth_source(self) -> str:
        """Name the delegated auth source (the OpenAI api-key profile).

        The adapter performs no credential acquisition. The codex CLI surface
        has no sanctioned headless subscription token, so this is api-key only;
        returning the source name lets the seam record provenance without
        re-implementing auth.
        """
        return _AUTH_SOURCE

    def build_command(self, ctx: RunContext) -> list[str]:
        """Return the ``codex exec --json`` argv for this run.

        The documented headless invocation (vendor-capabilities.md § OpenAI:
        ``codex exec --json``). The executable resolves via ``shutil.which``
        when present so the live path uses the same binary, and falls back to
        the bare ``"codex"`` token in unit tests / unresolved environments. The
        prompt is passed last, as ``codex exec`` expects.
        """
        executable = shutil.which("codex") or "codex"
        return [
            executable,
            "exec",
            "--json",
            ctx.prompt.strip(),
        ]

    def spawn(self, cmd: list[str], env: dict[str, str]) -> Iterable[str]:
        """Spawn the codex CLI and return native stdout lines.

        Left unimplemented in this task: the live subprocess bridge lands with
        the cutover (Task 4.7). Unit tests inject a fake ``spawn``; calling the
        real one before the cutover is a programming error.
        """
        raise NotImplementedError("OpenAICLI.spawn is wired to the live subprocess in Task 4.7")

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """Template run, but REFUSE first if the caller asks for live gating.

        ``require_operator_approval`` is a request to gate the run before tool
        execution -- which this observe-only surface cannot honor. Refusing here
        (rather than silently observing) makes the limitation explicit at the
        call site so a governed run is never misrouted to the CLI surface.
        """
        if ctx.require_operator_approval:
            self.require_live_gating()
        yield from super().run(ctx)

    def parse_stream(self, lines: Iterable[str], ctx: RunContext) -> Iterator[BackendEvent]:
        """Decode each native line, map it, and flush coalesced text last.

        JSON-decodes each non-empty ``codex exec --json`` line, maps it via
        ``map_native_event``, and emits the single coalesced ``assistant_text``
        once the stream ends (cumulative snapshots supersede; never concatenated).
        """
        self._coalescer = Coalescer()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            native: dict[str, Any] = json.loads(stripped)
            event = self.map_native_event(native)
            if event is not None:
                yield event
        # CLI snapshots carry no per-event run_id, so the run-less stream is
        # grouped under the ``None`` key (matching ``Coalescer``'s convention).
        flushed = self._coalescer.flush(None, source=_SOURCE)
        if flushed is not None:
            yield flushed

    def map_native_event(self, native: dict[str, Any]) -> BackendEvent | None:
        """Map ONE parsed codex ``thread``/``turn``/``item.*`` line to an event.

        Assistant ``item.completed`` text (``item.type=="assistant_message"``)
        is fed to the coalescer and returns ``None`` (emitted once at flush).
        A ``command_execution`` item maps to a ``tool.used`` event. The
        end-of-turn ``turn.completed`` maps to the single OBSERVE-ONLY receipt.
        ``thread.started`` / ``turn.started`` (and anything else) are dropped to
        keep the canonical stream clean.
        """
        kind = str(native.get("type") or "")
        if kind == "item.completed":
            return self._map_item(native.get("item"))
        if kind == "turn.completed":
            return _map_turn_receipt(native)
        return None

    def _map_item(self, item: Any) -> BackendEvent | None:
        if not isinstance(item, dict):
            return None
        item_type = str(item.get("type") or "")
        if item_type == "assistant_message":
            text = strip_contract_envelopes(str(item.get("text") or ""))
            if text:
                self._coalescer.update(None, text)
            return None
        if item_type == "command_execution":
            return _map_command_item(item)
        return None


def _map_command_item(item: dict[str, Any]) -> BackendEvent:
    return tool_event(
        tool="shell",
        source=_SOURCE,
        command=optional_str(item.get("command")),
    )


def _map_turn_receipt(native: dict[str, Any]) -> BackendEvent:
    # The codex CLI ran the side effect; craik OBSERVED and recorded the
    # reported result -- hence ``execution="delegated-observed"``. Crucially,
    # because the pre-tool hook does NOT fire (vendor-capabilities.md § OpenAI),
    # craik did NOT authorize the call pre-execution: the receipt attests
    # OBSERVATION only, so ``decided_by="bypass"`` (the ungoverned audit flag)
    # -- NOT the ``operator`` value the gating CLIs stamp. craik cannot enforce
    # a ``deny`` on this surface, so the observed verdict is recorded as
    # ``allow`` (the codex CLI already executed it).
    return receipt_event(
        receipt_id="receipt_openai_cli_observe",
        source=_SOURCE,
        purpose="execution",
        execution="delegated-observed",
        mode="default",
        decision="allow",
        decided_by=_OBSERVE_ONLY_DECIDED_BY,
    )


__all__ = ["LiveGatingUnsupported", "OpenAICLI"]
