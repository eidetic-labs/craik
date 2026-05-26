from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import CapabilityReceipt, ReceiptResult
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.modals.receipt_detail import receipt_detail_record
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.transcript_search import TranscriptSearchOverlay
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def test_transcript_search_overlay_tracks_matches_and_navigation() -> None:
    overlay = TranscriptSearchOverlay()

    overlay.open(["alpha receipt", "beta", "receipt gamma"])
    overlay.append_query("r")
    overlay.append_query("e")
    overlay.append_query("c")

    assert overlay.display
    assert overlay.state.query == "rec"
    assert overlay.state.matches == ("alpha receipt", "receipt gamma")

    overlay.move(1)
    assert overlay.state.index == 1

    overlay.backspace()
    assert overlay.state.query == "re"
    assert overlay.state.index == 0

    overlay.dismiss()
    assert not overlay.display


def test_ctrl_f_searches_current_transcript(tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            app._write_transcript("receipt alpha")
            app._write_transcript("other line")
            await pilot.press("ctrl+f")
            await pilot.press("r", "e", "c")

            overlay = app.query_one("#transcript-search", TranscriptSearchOverlay)
            assert overlay.display
            assert overlay.state.query == "rec"
            assert overlay.state.matches == ("receipt alpha",)

            await pilot.press("escape")
            assert not overlay.display

    asyncio.run(run())


def test_receipt_detail_modal_reads_redacted_receipt(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    try:
        store.put_receipt(_receipt("receipt_interactive"))
    finally:
        store.close()

    detail = receipt_detail_record("receipt_interactive", env=env)

    assert detail == {
        "id": "receipt_interactive",
        "found": True,
        "integrity": "verified receipt chain",
        "status": "passed",
        "summary": "Interactive receipt detail.",
    }


def test_receipt_detail_modal_reports_missing_receipt(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    store.close()

    detail = receipt_detail_record("missing_receipt", env=env)

    assert detail["id"] == "missing_receipt"
    assert detail["found"] is False
    assert detail["message"] == "receipt not found"


def _receipt(receipt_id: str) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=receipt_id,
        task_id="task_interactive",
        actor="agent:test",
        capability="shell.test",
        target="pytest",
        policy_profile="strict",
        reason="Validate interactive receipt display.",
        result=ReceiptResult(
            status="passed",
            summary="Interactive receipt detail.",
            metadata={},
        ),
        redacted=True,
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
    )
