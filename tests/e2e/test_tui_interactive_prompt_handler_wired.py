"""Verify production TUI slash dispatch wires canonical interactive prompts."""

from __future__ import annotations

import asyncio

import pytest
import typer

pytest.importorskip("textual")


def _registry_with_confirm_prompt():
    from craik.runtime.contract import CommandResult, craik_command
    from craik.runtime.contract.auto_registry import AutoSlashRegistry

    app = typer.Typer()

    @app.command("confirm-me")
    @craik_command(
        payload_shape="kv",
        interactive_prompts={"confirm_action": "ConfirmModal"},
    )
    def confirm_me() -> CommandResult:
        accepted = typer.confirm("Proceed?", default=False)
        return CommandResult(
            payload={"accepted": accepted},
            shape="kv",
            text=f"accepted={accepted}",
        )

    return AutoSlashRegistry.from_typer(app)


def test_tui_dispatch_passes_real_interactive_prompt_handler(tmp_path) -> None:
    """A metadata-backed Typer confirm opens a canonical modal in CraikApp."""

    async def run() -> None:
        from craik.runtime.shell.modals.confirm import ConfirmModal
        from craik.runtime.shell.textual_app import CraikApp
        from craik.runtime.shell.textual_widgets.craik_input import CraikInput

        app = CraikApp(
            env={"CRAIK_HOME": str(tmp_path / "home")},
            registry=_registry_with_confirm_prompt(),
        )
        async with app.run_test() as pilot:
            app.query_one("#input", CraikInput).value = "/confirm-me"
            await pilot.press("enter")

            for _ in range(20):
                await pilot.pause()
                if any(isinstance(screen, ConfirmModal) for screen in app.screen_stack):
                    break
            assert any(
                isinstance(screen, ConfirmModal) for screen in app.screen_stack
            ), (
                "Expected ConfirmModal, got "
                f"{[type(screen).__name__ for screen in app.screen_stack]}"
            )

            await pilot.click("#confirm-accept")
            for _ in range(20):
                await pilot.pause()
                if any("accepted=True" in line for line in app._transcript_lines):
                    break
            assert any("accepted=True" in line for line in app._transcript_lines)

    asyncio.run(run())
