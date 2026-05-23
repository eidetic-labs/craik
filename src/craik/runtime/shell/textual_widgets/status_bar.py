"""Bottom status bar for the canonical terminal UI."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

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

    def update_status(self, report: ReadinessReport, *, cwd: Path | None = None) -> None:
        mode = "audited" if report.operator_required else "single-operator"
        model = report.active_model or "no model"
        display_cwd = _tilde_path(cwd or Path.cwd())
        self.current_status = f"Craik · {model} · {report.state} · {mode} · {display_cwd}"
        self.update(f"[b]Craik[/b] · {model} · {report.state} · {mode} · {display_cwd}")


def _tilde_path(path: Path) -> str:
    try:
        home = Path.home()
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return path.as_posix()
