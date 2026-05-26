"""Smoke tests for canonical receipt detail modals."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from textual.app import App

from craik.contracts.models import CapabilityReceipt, ReceiptResult
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.modals.receipt_detail import ReceiptDetailModal, receipt_detail_record
from craik.runtime.store import LocalStore


def test_receipt_detail_record_reads_redacted_receipt(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    try:
        store.put_receipt(_receipt("receipt_modal"))
    finally:
        store.close()

    assert receipt_detail_record("receipt_modal", env=env) == {
        "id": "receipt_modal",
        "found": True,
        "integrity": "verified receipt chain",
        "status": "passed",
        "summary": "Modal receipt detail.",
    }


def test_receipt_detail_modal_closes_with_close_action(tmp_path: Path) -> None:
    env = _env(tmp_path)
    completed: list[str | None] = []

    async def run() -> None:
        class TestApp(App[None]):
            async def on_mount(self) -> None:
                self.push_screen(
                    ReceiptDetailModal("missing_receipt", env=env),
                    completed.append,
                )

        async with TestApp().run_test() as pilot:
            await pilot.pause()
            await pilot.press("tab")
            await pilot.press("enter")

    asyncio.run(run())

    assert completed == ["close"]


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def _receipt(receipt_id: str) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=receipt_id,
        task_id="task_modal",
        actor="agent:test",
        capability="shell.test",
        target="pytest",
        policy_profile="strict",
        reason="Validate receipt display.",
        result=ReceiptResult(
            status="passed",
            summary="Modal receipt detail.",
            metadata={},
        ),
        redacted=True,
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )
