from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

import pytest

from craik.runtime.shell import slash_commands
from craik.runtime.shell.readiness import ReadinessReport, next_actions, resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.accent_emission import AccentEmission
from craik.runtime.shell.textual_widgets.craik_input import CraikInput
from craik.runtime.shell.textual_widgets.footer_safe_area import FooterSafeArea
from craik.runtime.shell.textual_widgets.history_search import HistorySearchOverlay
from craik.runtime.shell.textual_widgets.run_activity_panel import RunActivityPanel
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.shell.textual_widgets.text_selection_hint import (
    SELECTION_HINT_MESSAGE,
    first_launch_selection_hint,
)
from craik.runtime.shell.textual_widgets.toast_queue import ToastQueue
from craik.runtime.shell.textual_widgets.working_indicator import WorkingIndicator


def test_v0125_bottom_stack_renders_in_locked_edge_order(tmp_path: Path) -> None:
    async def run() -> None:
        env = {"CRAIK_HOME": str(tmp_path / "home"), "CRAIK_TUI_SELECTION_HINT": "0"}
        async with CraikApp(env=env).run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            pilot.app.query_one(WorkingIndicator).display = True
            pilot.app.query_one(ToastQueue).push("selection hint")
            pilot.app.query_one(AccentEmission).update("x")
            await pilot.pause(0.1)

            footer = pilot.app.query_one(FooterSafeArea)
            status = pilot.app.query_one(StatusBar)
            accent = pilot.app.query_one(AccentEmission)
            input_widget = pilot.app.query_one(CraikInput)
            toast = pilot.app.query_one(ToastQueue)
            working = pilot.app.query_one(WorkingIndicator)

            assert footer.region.y > status.region.y
            assert status.region.y > accent.region.y
            assert accent.region.y > input_widget.region.y
            assert input_widget.region.y > toast.region.y
            assert toast.region.y > working.region.y
            assert footer.region.y - status.region.y == 1

    asyncio.run(run())


def test_v0125_history_overlay_has_region_snapshot_coverage(tmp_path: Path) -> None:
    async def run() -> None:
        env = {"CRAIK_HOME": str(tmp_path / "home"), "CRAIK_TUI_SELECTION_HINT": "0"}
        async with CraikApp(env=env).run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            overlay = pilot.app.query_one(HistorySearchOverlay)
            overlay.open()
            await pilot.pause(0.1)
            input_widget = pilot.app.query_one(CraikInput)

            assert overlay.region.y < input_widget.region.y

    asyncio.run(run())


def test_v0125_active_run_keeps_transcript_space_on_small_terminal(tmp_path: Path) -> None:
    async def run() -> None:
        env = {"CRAIK_HOME": str(tmp_path / "home"), "CRAIK_TUI_SELECTION_HINT": "0"}
        app = CraikApp(env=env)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.2)
            app._run_backend_label = "Claude Code"
            app._set_working(True)
            app._update_run_activity_from_message("Created task `task_update_docs`.")
            app._update_run_activity_from_message("Created run `run_update_docs`.")
            app._update_run_activity_from_message(
                "Claude Code is using `Read` on `docs/guides/terminal-ui.md`."
            )
            await pilot.pause(0.1)

            transcript = app.query_one("#transcript")
            activity = app.query_one(RunActivityPanel)
            input_widget = app.query_one(CraikInput)

            assert transcript.region.height >= 7
            assert activity.region.height == 5
            assert transcript.region.y < activity.region.y < input_widget.region.y

    asyncio.run(run())


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("/agent", ("/agent list", "/agent launch", "/agent rename", "/agent delete")),
        ("/session", ("/session list", "/session rename", "/session delete")),
        ("/receipts", ("/receipts list", "/receipts detail", "/receipts verify")),
    ],
)
def test_v0125_parent_slash_commands_list_subcommands(
    command: str,
    expected: tuple[str, ...],
    tmp_path: Path,
) -> None:
    result = dispatch_slash_command(command, env={"CRAIK_HOME": str(tmp_path / "home")})

    assert "requires a subcommand" in result.text
    for subcommand in expected:
        assert subcommand in result.text


def test_v0125_unknown_slash_command_still_suggests_help(tmp_path: Path) -> None:
    result = dispatch_slash_command("/zzznotreal", env={"CRAIK_HOME": str(tmp_path / "home")})

    assert "unknown slash command" in result.text


def test_v0125_unknown_slash_command_escapes_rich_markup(tmp_path: Path) -> None:
    result = dispatch_slash_command("/[red]oops", env={"CRAIK_HOME": str(tmp_path / "home")})

    assert "unknown slash command" in result.text
    assert "unknown slash command: /[red]" not in result.text
    assert r"\[red]" in result.text


def test_v0125_subcommand_listing_escapes_rich_markup(monkeypatch) -> None:
    monkeypatch.setitem(slash_commands.SUBCOMMAND_LISTINGS, "[red]agent", ("list",))

    result = slash_commands._subcommand_listing_response("[red]agent", ["/[red]agent"])

    assert result is not None
    assert "`/[red]" not in result
    assert r"\[red]" in result


def test_v0125_next_actions_split_tui_and_cli_shapes(tmp_path: Path) -> None:
    report = ReadinessReport(
        state="unconfigured",
        home=tmp_path,
        initialized=False,
        operator_required=False,
        operator_authenticated=False,
        provider_configured=False,
        local_model_configured=False,
        active_profile="default",
        active_model=None,
    )

    assert next_actions(report, in_tui=True) == [
        "use `/auth login <provider>`",
        "use `/model set <provider/model>`",
    ]
    assert next_actions(report, in_tui=False) == [
        "run craik auth login <provider>",
        "run craik model set <provider/model>",
    ]


def test_v0125_operator_required_next_action_uses_registered_slash_login(
    tmp_path: Path,
) -> None:
    report = ReadinessReport(
        state="unconfigured",
        home=tmp_path,
        initialized=False,
        operator_required=True,
        operator_authenticated=False,
        provider_configured=False,
        local_model_configured=False,
        active_profile="default",
        active_model=None,
    )

    assert next_actions(report, in_tui=True)[0] == "use `/login`"
    assert next_actions(report, in_tui=False)[0] == "run craik login"
    assert "Operator login" in dispatch_slash_command("/login").text


def test_v0125_resolve_readiness_uses_tui_next_actions(tmp_path: Path) -> None:
    report = resolve_readiness(
        {"CRAIK_HOME": str(tmp_path / "home")},
        in_tui=True,
    )

    assert "use `/auth login <provider>`" in report.next_actions
    assert "run craik auth login <provider>" not in report.next_actions


def test_v0125_tui_declares_text_selection_support() -> None:
    assert CraikApp.ALLOW_SELECT is True


def test_v0125_text_selection_hint_is_once_per_state_dir(tmp_path: Path) -> None:
    state = tmp_path / "home" / "state"
    state.mkdir(parents=True)
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    assert first_launch_selection_hint(env) == SELECTION_HINT_MESSAGE
    assert first_launch_selection_hint(env) is None
    marker = state / "tui-selection-hint.seen"
    assert marker.exists()
    if os.name == "posix":
        assert stat.S_IMODE(marker.stat().st_mode) == 0o600
