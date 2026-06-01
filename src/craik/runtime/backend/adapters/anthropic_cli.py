"""Real ``AnthropicCLI`` adapter: Claude Code stream-json -> typed events.

This is the Phase 4 exemplar concrete adapter. It subclasses
:class:`~craik.runtime.backend.adapters.base.CLIAdapter` and fills the three
abstract hooks (``build_command`` / ``spawn`` / ``map_native_event``) plus an
overridden ``parse_stream`` that coalesces cumulative assistant-text snapshots.

Composition over reinvention: the native Claude Code ``stream-json`` lines are
classified by the EXISTING ``_claude_stream_line_events`` parser (it yields the
``{"kind": ...}`` intermediate dicts the legacy path already understands), and
those intermediate dicts are translated to canonical :class:`BackendEvent`
records via the Phase-1 typed builders. The adapter therefore owns only the
translation table, not a second copy of the parser; the contract-strip and the
optional-string coercion are shared base helpers reused by every adapter.

This task builds + unit-tests the adapter in isolation; it is NOT yet wired
into the live ``execute_prompt`` path (that cutover is Task 4.7). The live
PreToolUse hook bridge (Phase 5) is represented here by a config point only --
``pre_tool_use_hook_config`` names where the hook would be registered; no live
daemon is started.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.adapters.base import (
    CLIAdapter,
    RunContext,
    optional_str,
    strip_contract_envelopes,
)
from craik.runtime.backend.adapters.hook_bridge import SOCKET_ENV, VENDOR_ENV
from craik.runtime.backend.adapters.vendor_profile import VendorProfile, vendor_profile
from craik.runtime.backend.claude_code_support import _claude_stream_line_events
from craik.runtime.backend.events import (
    BackendEvent,
    Coalescer,
    EventSource,
    ReceiptDecision,
    approval_resolved_event,
    receipt_event,
    tool_event,
)

if TYPE_CHECKING:
    from craik.runtime.backend.session import BackendPromptResult

# Originating-adapter identifier carried on every emitted event envelope.
_SOURCE: EventSource = "anthropic-cli"

# Auth is delegated to the existing Claude CLI subscription/OAuth marker
# profile; this adapter acquires NO credentials of its own. The token names the
# auth SOURCE only (the "anthropic_claude_cli" marker profile), satisfying the
# Phase-4 auth-naming requirement without re-implementing any OAuth flow.
_AUTH_SOURCE = "anthropic_claude_cli"


class AnthropicCLI(CLIAdapter):
    """Adapter that runs the Claude Code CLI and maps its stream to events.

    ``supports_live_gating`` is ``True``: the CLI gates tool calls at the
    PreToolUse hook boundary (wired live in Phase 5).
    """

    vendor = "anthropic"
    surface = "cli"

    def __init__(self, profile: VendorProfile | None = None) -> None:
        # ``select_adapter`` will inject the profile at construction in Task 4.7;
        # until then default to the canonical anthropic profile.
        self.vendor_profile: VendorProfile = profile or _default_anthropic_profile()
        # Phase-5 gating config: the REAL PreToolUse hook that registers the
        # ``craik-hook`` client as Claude Code's pre-tool command (anthropic-cli.md
        # §1/§3). The live ``spawn`` (PR B) writes this into ``.claude/settings.json``
        # and substitutes the real bridge socket path into ``env[CRAIK_HOOK_SOCKET]``
        # before launch; this object holds only the data structure + the env keys
        # the gateway must set -- no daemon is started here.
        self.pre_tool_use_hook_config: dict[str, Any] = _pre_tool_use_hook_config()
        # Per-run coalescer for cumulative assistant-text snapshots. Reset at
        # the start of every ``parse_stream`` so runs never bleed together.
        self._coalescer = Coalescer()

    def supports_live_gating(self) -> bool:
        return True

    def auth_source(self) -> str:
        """Name the delegated auth source (the Claude CLI marker profile).

        The adapter performs no credential acquisition: Claude Code owns its own
        subscription/OAuth session. This returns the marker-profile name so the
        seam can record provenance without re-implementing auth.
        """
        return _AUTH_SOURCE

    def build_command(self, ctx: RunContext) -> list[str]:
        """Return the Claude Code stream-json argv for this run.

        Mirrors the canonical launch in ``claude_code._execute_claude_code_prompt``
        (``--output-format stream-json --verbose``); the executable resolves via
        ``shutil.which`` when present so the live path uses the same binary, and
        falls back to the bare ``"claude"`` token in unit tests / unresolved
        environments. The prompt is passed with ``-p`` last, as the CLI expects.
        """
        executable = shutil.which("claude") or "claude"
        return [
            executable,
            "--output-format",
            "stream-json",
            "--verbose",
            "-p",
            ctx.prompt.strip(),
        ]

    def spawn(self, cmd: list[str], env: dict[str, str]) -> Iterable[str]:
        """Spawn the Claude CLI and return native stdout lines.

        Left unimplemented in this task: the live subprocess bridge lands with
        the cutover (Task 4.7) / Phase 5. Unit tests inject a fake ``spawn``;
        calling the real one before the cutover is a programming error.
        """
        raise NotImplementedError("AnthropicCLI.spawn is wired to the live subprocess in Task 4.7")

    def parse_stream(self, lines: Iterable[str], ctx: RunContext) -> Iterator[BackendEvent]:
        """Classify each native line, map it, and flush coalesced text last.

        Reuses ``_claude_stream_line_events`` for parsing/classification, maps
        each resulting ``{"kind": ...}`` intermediate via ``map_native_event``,
        and emits the single coalesced ``assistant_text`` once the stream ends
        (cumulative snapshots supersede; they are never concatenated).
        """
        self._coalescer = Coalescer()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            parsed_events, _final_text = _claude_stream_line_events(stripped)
            for native in parsed_events:
                event = self.map_native_event(native)
                if event is not None:
                    yield event
        # CLI snapshots carry no per-event run_id, so the run-less stream is
        # grouped under the ``None`` key (matching ``Coalescer``'s convention).
        flushed = self._coalescer.flush(None, source=_SOURCE)
        if flushed is not None:
            yield flushed

    def _legacy_run(
        self,
        ctx: RunContext,
        *,
        events: list[BackendEvent],
        source: str,
        env: dict[str, str] | None,
    ) -> BackendPromptResult:
        """Bridge to the legacy claude-code path (pre-cutover seam).

        ``execute_prompt`` still drives the live path through this bridge until
        the Task 4.7 cutover replaces it with ``run``; keeping it here preserves
        byte-identical behavior. ``source`` is accepted for signature symmetry
        with ``AnthropicAPI`` but is unused by the claude path. ``env`` is the
        ORIGINAL value (possibly None), threaded separately from ``ctx.env``.
        """
        # Lazy import: ``legacy_runs`` imports ``session``, which (lazily)
        # imports ``registry`` -> this module; keeping the import function-local
        # avoids an import cycle.
        from craik.runtime.backend.adapters.legacy_runs import _legacy_claude_code_run

        return _legacy_claude_code_run(
            prompt=ctx.prompt,
            env=env,
            emit=ctx.emit,
            events=events,
            require_operator_approval=ctx.require_operator_approval,
        )

    def map_native_event(self, native: dict[str, Any]) -> BackendEvent | None:
        """Map ONE parsed ``{"kind": ...}`` Claude event to a typed event.

        Assistant text is fed to the coalescer and returns ``None`` (emitted
        once at flush). Tool / approval / receipt kinds map to their builders.
        Everything else (output / system / tool_result / file_change / status)
        is dropped to keep the canonical stream clean.
        """
        kind = str(native.get("kind") or "")
        if kind == "assistant_text":
            text = strip_contract_envelopes(str(native.get("text") or ""))
            if text:
                self._coalescer.update(None, text)
            return None
        if kind == "tool_use":
            return _map_tool_use(native)
        # Live approval-request events are produced by the Phase 5 hook bridge;
        # mapped there with a verified event shape.
        if kind == "permission_denial":
            return _map_permission_denial(native)
        if kind == "result":
            return _map_result_receipt(native)
        return None


# The ``craik-hook`` console script (defined in pyproject, entry point
# ``craik.runtime.hooks.client:craik_hook_main``) is the pre-tool
# gating client the CLI invokes. The live spawn (PR B) resolves its absolute path
# and the real bridge socket; the matcher ``*`` registers it for every tool.
_HOOK_COMMAND = "craik-hook"


def _pre_tool_use_hook_config() -> dict[str, Any]:
    """Return the REAL Claude Code PreToolUse hook config for ``craik-hook``.

    Pure data: the live ``spawn`` (PR B) writes ``settings`` into
    ``.claude/settings.json`` (anthropic-cli.md §1: a ``PreToolUse`` hook pointing
    at craik's hook script) and exports ``env`` before launch, substituting the
    real socket path into ``env[CRAIK_HOOK_SOCKET]``. ``CRAIK_HOOK_VENDOR`` is
    fixed to ``anthropic`` so the client emits the Anthropic ``permissionDecision``
    /exit-2 dialect (anthropic-cli.md §3.4). The socket value is left empty here;
    no daemon is started in this task.
    """
    return {
        "event": "PreToolUse",
        "command": _HOOK_COMMAND,
        "env": {SOCKET_ENV: "", VENDOR_ENV: "anthropic"},
        # ``.claude/settings.json``-style entry the live spawn writes verbatim.
        "settings": {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": _HOOK_COMMAND}],
                    }
                ]
            }
        },
    }


def _default_anthropic_profile() -> VendorProfile:
    return vendor_profile("anthropic")


def _map_tool_use(native: dict[str, Any]) -> BackendEvent:
    return tool_event(
        tool=str(native.get("tool") or "tool"),
        source=_SOURCE,
        target=optional_str(native.get("target")),
        command=optional_str(native.get("command")),
    )


def _map_permission_denial(native: dict[str, Any]) -> BackendEvent:
    # A surfaced permission denial is an approval RESOLVED as a denial: the
    # Claude CLI vetoed the tool, and craik records the resolution.
    decision: ReceiptDecision = "deny"
    approval_id = optional_str(native.get("approval_id")) or "approval_claude_cli_denied"
    return approval_resolved_event(
        approval_id=approval_id,
        decision=decision,
        source=_SOURCE,
        decided_by="policy",
    )


def _map_result_receipt(native: dict[str, Any]) -> BackendEvent:
    # The Claude CLI ran the tool; craik authorized + OBSERVED it. Hence
    # ``execution="delegated-observed"``. ``purpose`` is a stable descriptor of
    # what the receipt attests (matching the canonical receipt shape); the
    # result text is informational and is NOT smuggled into the purpose field.
    return receipt_event(
        receipt_id="receipt_anthropic_cli_run",
        source=_SOURCE,
        purpose="execution",
        execution="delegated-observed",
        # TODO(Phase 5): thread the real permission mode
        # (ask/auto/acceptEdits/plan) from RunContext once the hook bridge
        # carries it.
        mode="default",
        decision="allow",
        decided_by="operator",
    )


__all__ = ["AnthropicCLI"]
