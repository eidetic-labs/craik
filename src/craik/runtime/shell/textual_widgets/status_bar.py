"""Bottom status bar for the canonical terminal UI."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from craik.runtime.auth.usage import ProviderQuotaStatus, TokenUsageStatus, UsageTier
from craik.runtime.shell.readiness import ReadinessReport


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
    ) -> None:
        mode = "audited" if report.operator_required else "single-operator"
        model = report.active_model or "no model"
        display_cwd = _tilde_path(cwd or Path.cwd())
        plain_segments = ["Craik", model, report.state, mode]
        rich_segments = ["[b]Craik[/b]", model, report.state, mode]
        if session_name:
            plain_segments.append(session_name)
            rich_segments.append(f"[b]{session_name}[/b]")
        if token_usage is not None:
            plain_segments.append(token_usage.display)
            rich_segments.append(_tier_markup(token_usage.display, token_usage.tier))
        if quota is not None and quota.available:
            plain_segments.append(quota.display)
            rich_segments.append(_tier_markup(quota.display, quota.tier))
        if auto_approve:
            plain_segments.append("auto-approve")
            rich_segments.append("[yellow]auto-approve[/yellow]")
        plain_segments.append(display_cwd)
        rich_segments.append(display_cwd)
        self.current_status = " · ".join(plain_segments)
        self.update(" · ".join(rich_segments))


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
