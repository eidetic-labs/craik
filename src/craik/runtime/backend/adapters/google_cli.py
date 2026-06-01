"""Real ``GoogleCLI`` adapter: Gemini CLI stream-json -> typed events.

A DELTA following the Phase-4 exemplar :mod:`anthropic_cli`. It subclasses
:class:`~craik.runtime.backend.adapters.base.CLIAdapter` and fills the three
abstract hooks (``build_command`` / ``spawn`` / ``map_native_event``) plus an
overridden ``parse_stream`` that coalesces cumulative assistant-text snapshots.
The base does the heavy lifting; this module owns only the Gemini CLI
``stream-json`` vocabulary -> canonical-event translation table.

The native Gemini CLI ``stream-json`` line kinds (``init`` / ``message`` /
``tool_use`` / ``tool_result`` / ``result``) are classified by a small focused
parser here -- there is no existing Gemini CLI stream parser to reuse (the
``runners.google_adapter`` is a preview/fixture handoff adapter, not a live
stream classifier) -- and each parsed kind is translated to a canonical
:class:`BackendEvent` via the Phase-1 typed builders. The contract-strip and the
optional-string coercion are shared base helpers reused by every adapter.

This task builds + unit-tests the adapter in isolation; it is NOT yet wired
into the live ``execute_prompt`` path (that cutover is Task 4.7). The live
BeforeTool hook bridge (Phase 5) is represented here by a config point only --
``before_tool_hook_config`` names where the hook would be registered; no live
daemon is started. The google CLI has no legacy ``execute_prompt`` branch (only
the anthropic ids route through one pre-cutover), so -- unlike the anthropic
exemplar -- this adapter carries no ``_legacy_run`` bridge.
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
    receipt_event,
    tool_event,
)

# Originating-adapter identifier carried on every emitted event envelope.
_SOURCE: EventSource = "google-cli"

# Auth is delegated to the existing google credential source (API key, or a
# Vertex service account) resolved by the auth subsystem -- NOT the OAuth
# headless flow. The token NAMES the auth source only (the google credential
# profile), satisfying the Phase-4 auth-naming requirement without
# re-implementing any auth flow.
_AUTH_SOURCE = "google-credential"

# Workspace-trust env flag set on the spawn env: the Gemini CLI prompts to trust
# a workspace before running tools, which would hang a headless run. Setting it
# pre-authorizes the (already operator-trusted) workspace so the headless stream
# does not block on an interactive trust prompt. craik still governs every tool
# at the BeforeTool hook boundary.
_WORKSPACE_TRUST_ENV = "GEMINI_CLI_TRUST_WORKSPACE"


class GoogleCLI(CLIAdapter):
    """Adapter that runs the Gemini CLI and maps its stream to events.

    ``supports_live_gating`` is ``True``: the CLI gates tool calls at the
    BeforeTool hook boundary (wired live in Phase 5).
    """

    vendor = "google"
    surface = "cli"

    def __init__(self, profile: VendorProfile | None = None) -> None:
        # ``select_adapter`` will inject the profile at construction in Task 4.7;
        # until then default to the canonical google profile.
        self.profile: VendorProfile = profile or vendor_profile("google")
        # Phase-5 config point: where the live BeforeTool gating hook is
        # registered. Held as inert config here -- no daemon is started.
        self.before_tool_hook_config: dict[str, str] = {
            "event": "BeforeTool",
            "transport": "craik.tui.gateway",
        }
        # Per-run coalescer for cumulative assistant-text snapshots. Reset at
        # the start of every ``parse_stream`` so runs never bleed together.
        self._coalescer = Coalescer()

    def supports_live_gating(self) -> bool:
        return True

    def auth_source(self) -> str:
        """Name the delegated auth source (the google credential profile).

        The adapter performs no credential acquisition: the Gemini CLI / the
        auth subsystem owns the API-key / Vertex service-account credential.
        This returns the source name so the seam can record provenance without
        re-implementing auth.
        """
        return _AUTH_SOURCE

    def build_command(self, ctx: RunContext) -> list[str]:
        """Return the Gemini CLI stream-json argv for this run.

        The executable resolves via ``shutil.which`` when present so the live
        path uses the same binary, and falls back to the bare ``"gemini"`` token
        in unit tests / unresolved environments. The prompt is passed with
        ``-p`` (non-interactive prompt mode), and ``--output-format stream-json``
        selects the machine-readable stream this adapter parses.
        """
        executable = shutil.which("gemini") or "gemini"
        return [
            executable,
            "-p",
            ctx.prompt.strip(),
            "--output-format",
            "stream-json",
        ]

    def spawn_env(self, env: dict[str, str]) -> dict[str, str]:
        """Return the spawn env with workspace trust pre-authorized.

        Copies ``env`` and sets ``GEMINI_CLI_TRUST_WORKSPACE=true`` so the
        headless run does not block on the CLI's interactive workspace-trust
        prompt (see ``_WORKSPACE_TRUST_ENV``). Pure / side-effect free: it
        returns a new dict rather than mutating the caller's env.
        """
        spawn_env = dict(env)
        spawn_env[_WORKSPACE_TRUST_ENV] = "true"
        return spawn_env

    def spawn(self, cmd: list[str], env: dict[str, str]) -> Iterable[str]:
        """Spawn the Gemini CLI and return native stdout lines.

        Left unimplemented in this task: the live subprocess bridge lands with
        the cutover (Task 4.7) / Phase 5. Unit tests inject a fake ``spawn``;
        calling the real one before the cutover is a programming error. When it
        lands, the spawn env is produced by ``spawn_env``.
        """
        raise NotImplementedError("GoogleCLI.spawn is wired to the live subprocess in Task 4.7")

    def parse_stream(self, lines: Iterable[str], ctx: RunContext) -> Iterator[BackendEvent]:
        """Decode each native line, map it, and flush coalesced text last.

        JSON-decodes each non-empty Gemini CLI ``stream-json`` line, maps it via
        ``map_native_event``, and emits the single coalesced ``assistant_text``
        once the stream ends (cumulative snapshots supersede; they are never
        concatenated).
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
        """Map ONE parsed Gemini CLI stream line to a typed event.

        Assistant ``message`` text is fed to the coalescer and returns ``None``
        (emitted once at flush). ``tool_use`` maps to a ``tool.used`` event; the
        end-of-run ``result`` line maps to the single delegated-observed
        receipt. ``tool_result`` (the tool's intermediate output) carries no
        other canonical signal, so it is dropped -- mirroring the exemplar
        ``AnthropicCLI``, which likewise drops its analogous intermediate and
        emits exactly one receipt from the end-of-run ``result``. ``init`` (and
        anything else) is dropped to keep the canonical stream clean.
        """
        kind = str(native.get("type") or "")
        if kind == "message":
            text = strip_contract_envelopes(str(native.get("text") or ""))
            if text:
                self._coalescer.update(None, text)
            return None
        if kind == "tool_use":
            return _map_tool_use(native)
        if kind == "result":
            return _map_result_receipt(native)
        return None


def _map_tool_use(native: dict[str, Any]) -> BackendEvent:
    return tool_event(
        tool=str(native.get("name") or "tool"),
        source=_SOURCE,
        target=optional_str(_target_from_input(native.get("input"))),
        command=optional_str(_command_from_input(native.get("input"))),
    )


def _target_from_input(tool_input: Any) -> str | None:
    if isinstance(tool_input, dict):
        return optional_str(tool_input.get("file_path") or tool_input.get("path"))
    return None


def _command_from_input(tool_input: Any) -> str | None:
    if isinstance(tool_input, dict):
        return optional_str(tool_input.get("command"))
    return None


def _map_result_receipt(native: dict[str, Any]) -> BackendEvent:
    # The Gemini CLI ran the tool; craik authorized + OBSERVED it. Hence
    # ``execution="delegated-observed"`` (the CLI observe model). ``purpose`` is
    # a stable descriptor of what the receipt attests (matching the canonical
    # receipt shape); the result text is informational and is NOT smuggled into
    # the purpose field.
    return receipt_event(
        receipt_id="receipt_google_cli_run",
        source=_SOURCE,
        purpose="execution",
        execution="delegated-observed",
        # TODO(Phase 5): thread the real permission mode from RunContext once
        # the BeforeTool hook bridge carries it.
        mode="default",
        decision="allow",
        decided_by="operator",
    )


__all__ = ["GoogleCLI"]
