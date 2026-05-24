from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

from craik.runtime.shell.readiness import ReadinessReport
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.accent_emission import AccentEmission
from craik.runtime.shell.textual_widgets.brand_tokens import CRAIK_GREY_400
from craik.runtime.shell.textual_widgets.footer_safe_area import FooterSafeArea
from craik.runtime.shell.textual_widgets.glyph_palette import (
    BULLET_SEPARATOR,
    DOT_LEADER,
    RECEIPT_OK,
    STATE_INFLIGHT,
)
from craik.runtime.shell.textual_widgets.history_search import HistorySearchOverlay
from craik.runtime.shell.textual_widgets.section_divider import SectionDivider
from craik.runtime.shell.textual_widgets.status_bar import StatusBar

ROOT = Path(__file__).resolve().parents[1]
WIDGET_ROOT = ROOT / "src/craik/runtime/shell/textual_widgets"
BRAND_HYGIENE_SCRIPT = ROOT / "scripts/check_codebase_brand_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_codebase_brand_hygiene", BRAND_HYGIENE_SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
brand_hygiene = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = brand_hygiene
SPEC.loader.exec_module(brand_hygiene)


def test_widget_glyphs_are_centralized_in_palette() -> None:
    disallowed = set("●○⚠✓✗▲└›─│═║╔╗╚╝")
    failures: list[str] = []
    for path in sorted(WIDGET_ROOT.glob("*.py")):
        if path.name == "glyph_palette.py":
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = "".join(sorted(set(line) & disallowed))
            if found:
                failures.append(f"{path.name}:{line_number}:{found}")

    assert failures == []


def test_status_bar_uses_bullet_separator_and_auto_approve_glyph() -> None:
    bar = StatusBar()
    report = _report()

    bar.update_status(report, auto_approve=True, session_name="Desk")

    assert f" {BULLET_SEPARATOR} " in bar.current_status
    assert "⚠ auto-approve" in bar.current_status
    assert "|" not in bar.current_status


def test_section_divider_uses_centered_dot_leader() -> None:
    divider = SectionDivider(width=20)

    assert DOT_LEADER in divider.current_divider
    assert "─" not in divider.current_divider


def test_theme_css_keeps_status_bar_low_contrast_without_background() -> None:
    for theme in ("dark", "light"):
        path = ROOT / f"src/craik/runtime/shell/textual_app_{theme}.tcss"
        content = path.read_text(encoding="utf-8")
        status_rule = _css_rule(content, ".status-bar")

        assert "background" not in status_rule
        assert "color: #A0A0A0" in status_rule or "color: #4A4A4A" in status_rule
        assert "#footer-safe-area" in content
        assert "height: 1" in _css_rule(content, "#footer-safe-area")


def test_textual_app_mounts_footer_safe_area_and_accent_emission(tmp_path: Path) -> None:
    async def run() -> None:
        env = {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}
        async with CraikApp(env=env).run_test() as pilot:
            assert pilot.app.query_one("#footer-safe-area", FooterSafeArea)
            accent = pilot.app.query_one("#accent-emission", AccentEmission)
            accent.flash("receipt")
            assert accent.current_glyph == RECEIPT_OK
            accent.flash("state")
            assert accent.current_glyph == STATE_INFLIGHT

    asyncio.run(run())


def test_operator_supplied_markup_is_rendered_literally() -> None:
    history = HistorySearchOverlay()
    history.search_query = "[red]query[/red]"
    history.matches = ["[blue]history[/blue]"]
    history.refresh_display()
    bar = StatusBar()
    bar.update_status(_report(), cwd=Path("/tmp/[red]cwd[/red]"))

    assert "[red]query[/red]" in str(history.render())
    assert "[blue]history[/blue]" in str(history.render())
    assert "[red]cwd[/red]" in str(bar.render())


def test_accent_emission_uses_animator_fade(tmp_path: Path) -> None:
    async def run() -> None:
        env = {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}
        async with CraikApp(env=env).run_test() as pilot:
            accent = pilot.app.query_one("#accent-emission", AccentEmission)
            accent.flash("receipt")
            assert accent.current_glyph == RECEIPT_OK
            await pilot.pause(1.5)
            assert accent.current_glyph == ""
            assert accent.styles.color.hex == CRAIK_GREY_400

    asyncio.run(run())


def test_brand_hygiene_guard_rejects_raw_widget_glyphs(tmp_path: Path) -> None:
    widget_root = tmp_path / "src/craik/runtime/shell/textual_widgets"
    scripts = tmp_path / "scripts"
    widget_root.mkdir(parents=True)
    scripts.mkdir(parents=True)
    (scripts / "_brand_hygiene_allowlist.txt").write_text("", encoding="utf-8")
    (widget_root / "glyph_palette.py").write_text('STATE_INFLIGHT = "●"\n', encoding="utf-8")
    (widget_root / "status_bar.py").write_text('STATUS = "● ready"\n', encoding="utf-8")

    assert brand_hygiene.codebase_brand_hygiene_failures(tmp_path) == [
        "src/craik/runtime/shell/textual_widgets/status_bar.py:1: "
        "raw TUI glyph '●'; import from glyph_palette.py"
    ]


def _css_rule(content: str, selector: str) -> str:
    start = content.index(selector)
    end = content.index("}", start)
    return content[start:end]


def _report() -> ReadinessReport:
    return ReadinessReport(
        state="fully-ready",
        home=ROOT,
        initialized=True,
        operator_required=False,
        operator_authenticated=False,
        provider_configured=True,
        local_model_configured=False,
        active_profile="default",
        active_model="openai/gpt-4o-mini",
        missing=[],
        next_actions=[],
    )
