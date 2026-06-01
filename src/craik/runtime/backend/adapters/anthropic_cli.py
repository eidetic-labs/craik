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

This adapter's typed ``run()`` is now the DEFAULT live ``execute_prompt`` path;
the legacy claude-code path is retained as the ``CRAIK_BACKEND_LEGACY_RUN=1``
fallback. The live PreToolUse hook bridge (Phase 5) is represented here by a
config point only -- ``pre_tool_use_hook_config`` names where the hook would be
registered; no live daemon is started.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.adapters.assistant_text import clean_assistant_text
from craik.runtime.backend.adapters.base import (
    CLIAdapter,
    RunContext,
    optional_str,
)
from craik.runtime.backend.adapters.hook_bridge import SOCKET_ENV, VENDOR_ENV
from craik.runtime.backend.adapters.vendor_profile import VendorProfile, vendor_profile
from craik.runtime.backend.claude_code_support import _claude_stream_line_events
from craik.runtime.backend.events import (
    BackendEvent,
    Coalescer,
    EventSource,
    ReceiptDecidedBy,
    ReceiptDecision,
    approval_resolved_event,
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

    def __init__(
        self,
        profile: VendorProfile | None = None,
        *,
        original_env: dict[str, str] | None = None,
    ) -> None:
        # ``select_adapter`` will inject the profile at construction in Task 4.7;
        # until then default to the canonical anthropic profile.
        self.vendor_profile: VendorProfile = profile or _default_anthropic_profile()
        # The ORIGINAL env (possibly None) the claude core needs -- threaded
        # separately from ``RunContext.env`` (which is coerced to ``{}``), exactly
        # as the legacy path threads ``env=`` separately (e.g.
        # ``LocalStore.from_env(None)`` vs ``from_env({})``). ``select_adapter``
        # injects this at the Task 5.7 cutover; tests set it directly.
        self.original_env: dict[str, str] | None = original_env
        # Live-gating hook overlay (Task 5.6): when the gateway opens a
        # ``hook_bridge_session`` for a gated run it sets this to the session's
        # ``{CRAIK_HOOK_SOCKET, CRAIK_HOOK_VENDOR}`` overlay. ``run`` merges it OVER
        # the env threaded to the claude core, so the claude subprocess env (built
        # by ``claude_code._claude_code_env`` from ``os.environ`` + this env) carries
        # the bridge address for the PreToolUse ``craik-hook`` client. ``None``
        # (default, and the only value pre-cutover) means no live bridge -- the env
        # is unchanged. The gateway sets it in Task 5.7; tests set it directly.
        self.hook_env: dict[str, str] | None = None
        # Phase-5 gating config: the REAL PreToolUse hook that registers the
        # ``craik-hook`` client as Claude Code's pre-tool command (anthropic-cli.md
        # §1/§3). The live ``spawn`` (PR B) writes this into ``.claude/settings.json``
        # and substitutes the real bridge socket path into ``env[CRAIK_HOOK_SOCKET]``
        # before launch; this object holds only the data structure + the env keys
        # the gateway must set -- no daemon is started here.
        self.pre_tool_use_hook_config: dict[str, Any] = _pre_tool_use_hook_config()
        # Payload-capture seam (Task 5.7): the generator-shaped run() stashes the
        # audited core payload here for ``execute_prompt`` to read.
        self.last_payload: dict[str, object] | None = None
        # Per-run governance attribution for the delegated-observed receipts
        # (parity item C). ``run()`` sets the honest value from the gating posture
        # before the stream starts; the conservative default is the ungated
        # ``"bypass"`` (never falsely ``operator``).
        self._decided_by: ReceiptDecidedBy = "bypass"
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

    def run(self, ctx: RunContext) -> Iterator[BackendEvent]:
        """Compose the audited claude core, yielding the NEW TYPED event sequence.

        This OVERRIDES the ``CLIAdapter`` template (build_command -> spawn ->
        parse_stream): the live claude run is executed + persisted by
        ``run_claude_code_core`` (the core spawns the subprocess), NOT by this
        adapter's ``spawn``. ``run()`` only re-shapes EMISSION -- it is the typed
        counterpart of ``legacy_runs._legacy_claude_code_run``, deriving NEW typed
        events from the SAME ``ClaudeCoreResult`` the legacy layer derives OLD
        events from.

        Sequence:
          1. The core streams each native claude line to an injected sink; the
             sink maps it through THIS adapter's ``map_native_event`` (+ the
             per-run ``Coalescer``), so assistant-text snapshots coalesce and
             tool / approval / receipt kinds become typed events. Those typed
             native events are buffered (the sink is push; ``run`` is a
             generator) and yielded first, followed by the single coalesced
             ``assistant_text``.
          2. After the core returns, the framing events (``run.started`` /
             per-receipt ``receipt.created`` with ``execution=delegated-observed``
             / ``run.completed``) are derived from the result and yielded.

        ``build_command`` / ``spawn`` / ``parse_stream`` are retained as the
        abstract CLI surface (still exercised by the Phase-4 fixture tests) but
        are NOT on this live path. This ``run()`` IS the live ``execute_prompt``
        path; the legacy claude-code path is the ``CRAIK_BACKEND_LEGACY_RUN=1``
        fallback.
        """
        from craik.runtime.backend.adapters.audited_core import (
            claude_framing_events,
            cli_observed_decided_by,
            run_claude_code_core,
            typed_claude_stream_sink,
        )

        # Parity item C (Task 5.7): the receipt governance attribution is honest
        # to whether this run was actually gated. The framing receipts
        # (``claude_framing_events``, derived from the core's persisted receipt
        # ids WITH ``run_id``) read it; set it for the whole run BEFORE the core
        # streams a single line.
        self._decided_by = cli_observed_decided_by(ctx.require_operator_approval)
        self._coalescer = Coalescer()
        native_events: list[BackendEvent] = []
        sink = typed_claude_stream_sink(
            map_native=self.map_native_event,
            coalescer=self._coalescer,
            sink=native_events.append,
        )
        core = run_claude_code_core(
            prompt=ctx.prompt,
            # The ORIGINAL env (possibly None), threaded like the legacy path,
            # with the live-gating overlay merged OVER it WHEN a bridge is active
            # (Task 5.6 seam). ``hook_env`` is ``None`` pre-cutover, so this is the
            # unchanged original env until the gateway sets it in Task 5.7.
            env=_merge_hook_env(self.original_env, self.hook_env),
            require_operator_approval=ctx.require_operator_approval,
            stream=sink,
        )
        self.last_payload = core.payload
        # Assemble the full typed sequence first so the gateway-event-history
        # artifact (parity item C: the 5.5a review flagged AnthropicCLI omitted
        # it) is persisted with the SAME events the run yields -- matching the
        # provider (``run_provider_typed``) and generic-CLI (``run_cli_typed``)
        # paths, which both persist it.
        events: list[BackendEvent] = list(native_events)
        flushed = self._coalescer.flush(None, source=_SOURCE)
        if flushed is not None:
            events.append(flushed)
        events.extend(claude_framing_events(core, source=_SOURCE, decided_by=self._decided_by))
        from craik.runtime.backend import session

        session._persist_gateway_event_history(core.payload, events, env=self.original_env)
        yield from events

    def _legacy_run(
        self,
        ctx: RunContext,
        *,
        events: list[BackendEvent],
        source: str,
        env: dict[str, str] | None,
    ) -> BackendPromptResult:
        """Bridge to the legacy claude-code path (``CRAIK_BACKEND_LEGACY_RUN`` fallback).

        ``run`` is now the default live ``execute_prompt`` path; this bridge is
        the opt-in fallback selected by ``CRAIK_BACKEND_LEGACY_RUN=1``, kept here
        because it preserves byte-identical behavior. ``source`` is accepted for
        signature symmetry
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
            text = clean_assistant_text(str(native.get("text") or ""))
            if text:
                self._coalescer.update(None, text)
            return None
        if kind == "tool_use":
            return _map_tool_use(native)
        # Live approval-request events are produced by the Phase 5 hook bridge;
        # mapped there with a verified event shape.
        if kind == "permission_denial":
            return _map_permission_denial(native)
        # The end-of-run ``result`` line is DROPPED here: the canonical
        # ``receipt.created`` is owned by ``claude_framing_events`` (derived from
        # the core's REAL persisted receipt ids, WITH ``run_id``). Synthesizing a
        # second receipt here produced a run-id-less, hardcoded-id record that the
        # gateway event contract rejects (``receipt.created`` requires a non-empty
        # ``run_id``) -- crashing the session. See ``test_cli_receipt_run_id_guard``.
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


def _merge_hook_env(
    original_env: dict[str, str] | None,
    hook_env: dict[str, str] | None,
) -> dict[str, str] | None:
    """Merge the live-gating ``hook_env`` overlay OVER ``original_env``.

    Returns ``original_env`` unchanged when there is no overlay (the pre-cutover
    case, so byte-identical to the legacy threading). When an overlay is present
    it wins on key collision -- it is the authoritative bridge address. A ``None``
    original env with an overlay becomes just the overlay (merged onto the
    subprocess env by ``claude_code._claude_code_env``).
    """
    if not hook_env:
        return original_env
    return {**(original_env or {}), **hook_env}


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


__all__ = ["AnthropicCLI"]
