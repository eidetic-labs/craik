from __future__ import annotations

import asyncio
from pathlib import Path

from craik.contracts.models import CapabilityReceipt
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.confirm_modal import ConfirmModal
from craik.runtime.shell.textual_widgets.craik_input import CraikInput
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def test_clear_slash_opens_confirmation_modal(tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            app.query_one("#input", CraikInput).value = "/clear"
            await pilot.press("enter")

            assert isinstance(app.screen, ConfirmModal)

    asyncio.run(run())


def test_clear_confirmation_yes_clears_transcript_and_records_receipt(tmp_path: Path) -> None:
    env = _env(tmp_path)

    async def run() -> None:
        app = CraikApp(env=env)
        async with app.run_test() as pilot:
            app._write_transcript("line to clear")
            app.query_one("#input", CraikInput).value = "/clear"
            await pilot.press("enter")
            await pilot.click("#confirm-yes")
            await pilot.pause()

            assert app.query_one("#input", CraikInput).value == ""
            assert app._transcript_lines == ["Transcript cleared. Receipts remain audited."]

    asyncio.run(run())

    receipts = _confirmation_receipts(env)
    assert len(receipts) == 1
    assert receipts[0].result.metadata["command"] == "/clear"
    assert receipts[0].result.metadata["decision"] == "confirmed"


def test_clear_confirmation_no_keeps_transcript_and_records_receipt(tmp_path: Path) -> None:
    env = _env(tmp_path)

    async def run() -> None:
        app = CraikApp(env=env)
        async with app.run_test() as pilot:
            app._write_transcript("line to keep")
            app.query_one("#input", CraikInput).value = "/clear"
            await pilot.press("enter")
            await pilot.click("#confirm-no")
            await pilot.pause()

            assert "line to keep" in app._transcript_lines
            assert app.query_one("#input", CraikInput).value == ""

    asyncio.run(run())

    receipts = _confirmation_receipts(env)
    assert len(receipts) == 1
    assert receipts[0].result.metadata["decision"] == "declined"


def _confirmation_receipts(env: dict[str, str]) -> list[CapabilityReceipt]:
    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    try:
        return [
            receipt
            for receipt in store.list_receipts()
            if receipt.capability == "slash.confirmation"
        ]
    finally:
        store.close()
