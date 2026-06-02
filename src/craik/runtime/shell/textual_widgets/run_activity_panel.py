"""Compact live activity panel for in-flight TUI runs."""

from __future__ import annotations

from dataclasses import dataclass

from rich.markup import escape
from textual.widgets import Static

from craik.runtime.shell.textual_widgets.glyph_palette import BULLET_SEPARATOR, STATE_INFLIGHT


@dataclass(frozen=True, slots=True)
class RunActivityState:
    """Small operator-facing snapshot of current run activity."""

    backend: str = "model"
    elapsed_seconds: int = 0
    mode: str | None = None
    phase: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    current_tool: str | None = None
    current_target: str | None = None
    files: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    last_event: str | None = None
    recent_events: tuple[str, ...] = ()
    approvals: int = 0
    denials: int = 0
    queued: int = 0


class RunActivityPanel(Static):
    """Render concise live run state without replacing the transcript."""

    DEFAULT_CSS = """
    RunActivityPanel {
        dock: bottom;
        height: 5;
        padding: 0 1;
        border: round #6F6A8F;
        color: #CFCFCF;
    }
    """

    current_state = RunActivityState()

    def update_activity(self, state: RunActivityState) -> None:
        self.current_state = state
        self.update(_render_state(state))


def _render_state(state: RunActivityState) -> str:
    minutes, remainder = divmod(max(0, state.elapsed_seconds), 60)
    elapsed = f"{minutes}m {remainder}s" if minutes else f"{remainder}s"
    head = [
        f"{STATE_INFLIGHT} {escape(state.backend)}",
        f"running {elapsed}",
        "Ctrl+C stop",
    ]
    if state.mode:
        head.append(f"mode {escape(_mode_posture(state.mode))}")
    if state.phase:
        head.append(f"phase {escape(state.phase)}")
    identity = []
    if state.task_id:
        identity.append(f"task {escape(state.task_id)}")
    if state.run_id:
        identity.append(f"run {escape(state.run_id)}")
    detail = []
    if state.current_tool:
        detail.append(f"tool {escape(state.current_tool)}")
    if state.current_target:
        detail.append(f"target {escape(state.current_target)}")
    if state.approvals or state.denials:
        detail.append(f"approvals {state.approvals}")
        detail.append(f"denials {state.denials}")
    if state.queued:
        detail.append(f"queued {state.queued}")
    if not detail:
        detail.append("waiting for first event")
    files = _limited_list("files", state.files)
    commands = _limited_list("commands", state.commands)
    recent_events = state.recent_events or ((state.last_event,) if state.last_event else ())
    recent = _recent_line(recent_events)
    identity_detail = (
        BULLET_SEPARATOR.join(identity + detail)
        if identity or detail
        else "waiting for first event"
    )
    return (
        f"[b]{BULLET_SEPARATOR.join(head)}[/b]\n"
        f"{identity_detail}\n"
        f"{files} {BULLET_SEPARATOR} {commands}\n"
        f"[dim]{recent}[/dim]"
    )


def _limited_list(label: str, values: tuple[str, ...], *, limit: int = 3) -> str:
    if not values:
        return f"{label} none"
    visible = [f"`{escape(value)}`" for value in values[:limit]]
    suffix = f" +{len(values) - limit}" if len(values) > limit else ""
    return f"{label} {', '.join(visible)}{suffix}"


def _mode_posture(mode: str) -> str:
    normalized = mode.lower()
    if normalized == "plan":
        return "Plan (preview only)"
    if normalized in {"accept edits", "auto edit"}:
        return "Accept edits (writes allowed)"
    if normalized in {"read-only"}:
        return "Read-only (sandbox)"
    if normalized in {"workspace write"}:
        return "Workspace write (sandbox writes)"
    # High-risk bypass-equivalents across vendors (bypassPermissions / yolo /
    # full access).
    if normalized in {"bypass", "yolo", "full access"}:
        return f"{mode} (gates bypassed)"
    return mode


def _recent_line(events: tuple[str | None, ...]) -> str:
    values = [escape(str(event)) for event in events if event]
    if not values:
        return "recent No model activity yet."
    return "recent " + " -> ".join(values[-3:])
