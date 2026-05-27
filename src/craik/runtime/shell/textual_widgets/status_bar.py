"""Bottom status bar for the canonical terminal UI."""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual.widgets import Static

from craik.runtime.auth.usage import ProviderQuotaStatus, TokenUsageStatus, UsageTier
from craik.runtime.shell.readiness import ReadinessReport
from craik.runtime.shell.textual_widgets.glyph_palette import (
    AUTO_APPROVE_GLYPH,
    BULLET_SEPARATOR,
)


class StatusBar(Static):
    """Render model, readiness state, operator mode, and cwd at screen bottom."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    """

    current_status: str = ""

    def update_status(
        self,
        report: ReadinessReport,
        *,
        cwd: Path | None = None,
        token_usage: TokenUsageStatus | None = None,
        quota: ProviderQuotaStatus | None = None,
        auto_approve: bool = False,
        session_name: str | None = None,
        claude_mode: str | None = None,
        backend: str | None = None,
        run_state: str | None = None,
    ) -> None:
        mode = "audited" if report.operator_required else "single-operator"
        model = report.active_model or "no model"
        rich_model = escape(model)
        rich_state = escape(report.state)
        display_cwd = _tilde_path(cwd or Path.cwd())
        rich_cwd = escape(display_cwd)
        plain_segments = ["Craik", model, report.state, mode]
        rich_segments = ["[b]Craik[/b]", rich_model, rich_state, mode]
        if session_name:
            plain_segments.append(session_name)
            rich_segments.append(f"[b]{escape(session_name)}[/b]")
        if claude_mode:
            plain_segments.append(f"Claude {claude_mode}")
            rich_segments.append(f"[green]Claude {escape(claude_mode)}[/green]")
        if backend:
            plain_segments.append(backend)
            rich_segments.append(f"[cyan]{escape(backend)}[/cyan]")
        if run_state:
            plain_segments.append(run_state)
            rich_segments.append(f"[yellow]{escape(run_state)}[/yellow]")
        if token_usage is not None:
            plain_segments.append(token_usage.display)
            rich_segments.append(_tier_markup(token_usage.display, token_usage.tier))
        if quota is not None and quota.available:
            plain_segments.append(quota.display)
            rich_segments.append(_tier_markup(quota.display, quota.tier))
        if auto_approve:
            plain_segments.append(f"{AUTO_APPROVE_GLYPH} auto-approve")
            rich_segments.append(f"[yellow]{AUTO_APPROVE_GLYPH} auto-approve[/yellow]")
        plain_segments.append(display_cwd)
        rich_segments.append(rich_cwd)
        separator = f" {BULLET_SEPARATOR} "
        self.current_status = separator.join(plain_segments)
        self.update(separator.join(rich_segments))


def _tilde_path(path: Path) -> str:
    try:
        home = Path.home()
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return path.as_posix()


def _tier_markup(value: str, tier: UsageTier) -> str:
    color = {
        "green": "green",
        "yellow": "yellow",
        "orange": "dark_orange",
        "red": "red",
        "unknown": "dim",
    }[tier]
    return f"[{color}]{value}[/{color}]"
