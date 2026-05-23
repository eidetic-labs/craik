"""Dependency-free terminal UI surface for Craik."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from craik.runtime.auth.login import auth_status_payload
from craik.runtime.i18n.messages import text as localize_text
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.policy.redaction import redact
from craik.runtime.policy.text import sanitize_runtime_text
from craik.runtime.shell.agent_shell import one_shot_response
from craik.runtime.shell.readiness import ReadinessReport, resolve_readiness
from craik.runtime.shell.slash_commands import (
    SlashCommandResult,
    command_names,
    dispatch_slash_command,
)
from craik.runtime.store import DATABASE_NAME, LocalStore


@dataclass(frozen=True)
class TuiPanel:
    """One rendered TUI panel."""

    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class TuiSnapshot:
    """Read-only terminal UI state assembled from existing runtime surfaces."""

    readiness: ReadinessReport
    panels: tuple[TuiPanel, ...]
    autocomplete: tuple[str, ...]
    redacted: bool = True


@dataclass(frozen=True)
class TuiStoreSummary:
    """Small read-only counts used by the TUI status panels."""

    sessions: int = 0
    runs: int = 0
    handoffs: int = 0
    receipts: int = 0
    approvals: int = 0
    gateway_states: tuple[str, ...] = ()
    skill_proposals: int = 0
    warnings: tuple[str, ...] = ()


@dataclass
class MultilineComposer:
    """Collect multiline input until a single-dot sentinel is received."""

    active: bool = False
    lines: list[str] = field(default_factory=list)

    def accept(self, text: str) -> tuple[bool, str | None]:
        """Accept one input line and return a completed message when ready."""
        if text == "/compose":
            self.active = True
            self.lines.clear()
            return True, None
        if not self.active:
            return False, text
        if text == ".":
            self.active = False
            completed = "\n".join(self.lines).strip()
            self.lines.clear()
            return True, completed
        self.lines.append(text)
        return True, None


def build_tui_snapshot(env: dict[str, str] | None = None) -> TuiSnapshot:
    """Build a deterministic TUI snapshot that can render before auth or setup."""
    readiness = resolve_readiness(env)
    summary = _store_summary(env)
    panels = (
        _status_panel(readiness, env),
        _auth_panel(env),
        _composer_panel(env),
        _model_panel(readiness, env),
        _session_panel(summary),
        _approval_panel(summary),
        _artifact_panel(summary),
        _gateway_panel(summary),
        _skill_panel(summary),
    )
    return TuiSnapshot(
        readiness=readiness,
        panels=panels,
        autocomplete=tuple(f"/{name}" for name in command_names()),
    )


def render_tui_snapshot(snapshot: TuiSnapshot, *, width: int = 88) -> str:
    """Render a nonblank ASCII TUI frame for terminals and snapshot tests."""
    safe_width = max(40, min(width, 120))
    title = f" {localize_text('tui.title')} "
    border = "+" + "-" * (safe_width - 2) + "+"
    lines = [
        border,
        "|" + title.center(safe_width - 2) + "|",
        border,
    ]
    for panel in snapshot.panels:
        lines.extend(_render_panel(panel, width=safe_width))
    lines.append(_frame_line("Autocomplete: " + ", ".join(snapshot.autocomplete[:8]), safe_width))
    lines.append(_frame_line("Redaction: on", safe_width))
    lines.append(border)
    return "\n".join(lines)


def render_approval_modal(
    *,
    approval_id: str,
    capability: str,
    target: str,
    risk: str,
    policy: str,
    operator: str | None = None,
    retry_path: str = "retry the blocked command after approval",
) -> str:
    """Render the approval modal fixture shared by TUI tests and docs."""
    panel = TuiPanel(
        "Approval",
        (
            f"ID: {_safe(approval_id)}",
            f"Capability: {_safe(capability)}",
            f"Target: {_safe(target)}",
            f"Risk: {_safe(risk)}",
            f"Policy: {_safe(policy)}",
            f"Operator: {_safe(operator or 'unassigned')}",
            f"Retry: {_safe(retry_path)}",
            "Actions: approve | deny | inspect receipt",
        ),
    )
    return "\n".join(_render_panel(panel, width=72))


def complete_tui_command(prefix: str) -> list[str]:
    """Return slash-command completions for TUI autocomplete."""
    normalized = prefix if prefix.startswith("/") else f"/{prefix}"
    return [
        f"/{name}"
        for name in command_names()
        if f"/{name}".startswith(normalized)
    ]


def run_tui(
    *,
    env: dict[str, str] | None = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    stdin_isatty: bool | None = None,
    lines: Iterable[str] | None = None,
) -> int:
    """Run the terminal UI, falling back to a single render in noninteractive mode."""
    output_func(render_tui_snapshot(build_tui_snapshot(env)))
    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    scripted = iter(lines) if lines is not None else None
    if not interactive and scripted is None:
        return 0

    composer = MultilineComposer()
    while True:
        try:
            prompt = "craik:tui... " if composer.active else "craik:tui> "
            raw = next(scripted) if scripted is not None else input_func(prompt)
        except (EOFError, StopIteration):
            return 0
        text = raw.rstrip()
        handled, completed = composer.accept(text)
        if handled and completed is None:
            if text == "/compose":
                output_func("Composer: enter text; finish with a single '.' line.")
            continue
        if completed is not None:
            text = completed
        else:
            text = text.strip()
        if not text:
            continue
        result = dispatch_tui_input(text, env=env)
        output_func(result.text)
        if result.exit_shell:
            return result.exit_code


def dispatch_tui_input(text: str, *, env: dict[str, str] | None = None) -> SlashCommandResult:
    """Dispatch one TUI input line through slash commands or prompt execution."""
    if text in {"/interrupt", "/stop"}:
        return SlashCommandResult("TUI interrupt requested; current run will stop at boundary.")
    if text.startswith("/redirect "):
        target = _safe(text.removeprefix("/redirect ").strip())
        return SlashCommandResult(f"TUI redirect queued for {target}.")
    if text == "/redraw":
        return SlashCommandResult(render_tui_snapshot(build_tui_snapshot(env)))
    if text.startswith("/"):
        return dispatch_slash_command(text, env=env)
    return SlashCommandResult("Streaming output\n" + one_shot_response(text, env=env))


def _status_panel(readiness: ReadinessReport, env: dict[str, str] | None) -> TuiPanel:
    lines = [
        f"State: {readiness.state}",
        f"Home: {_safe(str(readiness.home))}",
        f"Profile: {_safe(readiness.active_profile)}",
        f"Model: {_safe(readiness.active_model or 'not selected')}",
    ]
    if readiness.missing:
        lines.append("Missing: " + ", ".join(_safe(item) for item in readiness.missing))
    if readiness.warnings:
        lines.extend(f"Warning: {_safe(warning)}" for warning in readiness.warnings)
    lines.append("Next: " + _safe(readiness.next_actions[0]))
    return TuiPanel(localize_text("tui.status", env=env), tuple(lines))


def _composer_panel(env: dict[str, str] | None) -> TuiPanel:
    return TuiPanel(
        localize_text("tui.composer", env=env),
        (
            "Use /compose for multiline input; finish with '.'.",
            localize_text("tui.help", env=env),
            "Autocomplete source: shared slash-command registry.",
        ),
    )


def _auth_panel(env: dict[str, str] | None) -> TuiPanel:
    try:
        rows = auth_status_payload(env)
    except Exception:
        rows = []
    if not rows:
        lines: tuple[str, ...] = (
            "Providers: none configured",
            "Commands: /auth login <provider>, /auth status, craik auth login <provider>",
            "Shortcut: Ctrl-A opens auth capture in interactive frontends.",
        )
    else:
        lines = tuple(
            f"{row['id']}: {row['health_status']} via {row.get('backend') or row['kind']}"
            for row in rows[:4]
        )
    return TuiPanel(localize_text("tui.auth", env=env), lines)


def _model_panel(readiness: ReadinessReport, env: dict[str, str] | None) -> TuiPanel:
    return TuiPanel(
        localize_text("tui.model_picker", env=env),
        (
            f"Active: {_safe(readiness.active_model or 'not selected')}",
            "Commands: /model, craik model list, craik model set <provider/model>",
        ),
    )


def _session_panel(summary: TuiStoreSummary) -> TuiPanel:
    return TuiPanel(
        "Session Picker",
        (
            f"Sessions: {summary.sessions}",
            f"Runs: {summary.runs}",
            "Commands: /sessions, /resume <session-id>",
        ),
    )


def _approval_panel(summary: TuiStoreSummary) -> TuiPanel:
    return TuiPanel(
        "Approvals",
        (
            f"Open: {summary.approvals}",
            "Commands: /approvals, craik approvals approve|deny, inspect receipt.",
        ),
    )


def _artifact_panel(summary: TuiStoreSummary) -> TuiPanel:
    return TuiPanel(
        "Runs / Handoffs / Receipts",
        (
            f"Handoffs: {summary.handoffs}",
            f"Receipts: {summary.receipts}",
            "Panels preserve redaction and show IDs, status, and summaries only.",
        ),
    )


def _gateway_panel(summary: TuiStoreSummary) -> TuiPanel:
    states = ", ".join(summary.gateway_states) if summary.gateway_states else "not configured"
    return TuiPanel(
        "Gateway",
        (
            f"State: {_safe(states)}",
            "Commands: /gateway, craik gateway status",
        ),
    )


def _skill_panel(summary: TuiStoreSummary) -> TuiPanel:
    return TuiPanel(
        "Skill Proposals",
        (
            f"Proposals: {summary.skill_proposals}",
            "Commands: /skills, craik skills telemetry, craik skills promote",
        ),
    )


def _store_summary(env: dict[str, str] | None) -> TuiStoreSummary:
    paths = resolve_craik_paths(env)
    if not (paths.state / DATABASE_NAME).exists():
        return TuiStoreSummary()
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        return TuiStoreSummary(
            sessions=_count(store, "list_agent_session_states"),
            runs=_count(store, "list_task_runs"),
            handoffs=_count(store, "list_handoffs"),
            receipts=_count(store, "list_receipts") + _count(store, "list_plugin_receipts"),
            approvals=len(
                [
                    delegation
                    for delegation in _safe_list(store, "list_human_delegations")
                    if getattr(delegation, "kind", None) == "approval"
                    and getattr(delegation, "status", None) == "open"
                ]
            ),
            gateway_states=tuple(
                _safe(getattr(state, "status", "unknown"))
                for state in _safe_list(store, "list_gateway_runtime_states")
            ),
            skill_proposals=_count(store, "list_distilled_instruction_proposals"),
        )
    except Exception as error:
        return TuiStoreSummary(warnings=(f"store unavailable: {type(error).__name__}",))
    finally:
        store.close()


def _count(store: LocalStore, method_name: str) -> int:
    return len(_safe_list(store, method_name))


def _safe_list(store: LocalStore, method_name: str) -> list[Any]:
    method = getattr(store, method_name)
    value = method()
    return list(value)


def _render_panel(panel: TuiPanel, *, width: int) -> list[str]:
    lines = [_frame_line(f"[{panel.title}]", width)]
    if not panel.lines:
        return [*lines, _frame_line("- none", width)]
    lines.extend(_frame_line(line, width) for line in panel.lines)
    return lines


def _frame_line(text: str, width: int) -> str:
    safe = _safe(text)
    inner = safe[: width - 5]
    return "| " + inner.ljust(width - 4) + " |"


def _safe(value: str) -> str:
    return sanitize_runtime_text(str(redact(value).value))
