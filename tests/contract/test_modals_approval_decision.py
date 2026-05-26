"""Smoke tests for canonical approval decision modal."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from textual.app import App
from textual.widgets import Button, Input, Static

from craik.runtime.paths import ensure_craik_home
from craik.runtime.reviewing.approvals import open_approval_request
from craik.runtime.shell.modals.approval_decision import (
    ApprovalDecisionModal,
    ApprovalDecisionResult,
)
from craik.runtime.store import LocalStore


def test_approval_decision_modal_opens_with_expected_state(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _seed_approval(env, "approval_initial")
    completed: list[ApprovalDecisionResult | None] = []

    async def run() -> None:
        class TestApp(App[None]):
            async def on_mount(self) -> None:
                self.push_screen(
                    ApprovalDecisionModal("approval_initial", env=env),
                    completed.append,
                )

        async with TestApp().run_test() as pilot:
            await pilot.pause()
            summary = pilot.app.screen.query_one("#approval-summary", Static).render()
            reason = pilot.app.screen.query_one("#approval-reason", Input)
            buttons = {
                button.id
                for button in pilot.app.screen.query(Button)
                if button.id is not None
            }

            assert "Capability: shell.execute" in str(summary)
            assert "Target: npm test" in str(summary)
            assert reason.value == ""
            assert {"approval-cancel", "approval-deny", "approval-approve"} <= buttons

    asyncio.run(run())

    assert completed == []


def test_approval_decision_modal_approves_and_denies_requests(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _seed_approval(env, "approval_approve")
    _seed_approval(env, "approval_deny")
    completed: list[ApprovalDecisionResult | None] = []

    async def run() -> None:
        class TestApp(App[None]):
            pass

        async with TestApp().run_test() as pilot:
            await pilot.app.push_screen(
                ApprovalDecisionModal("approval_approve", env=env),
                completed.append,
            )
            await pilot.pause()
            pilot.app.screen.query_one("#approval-reason", Input).value = "scope is bounded"
            await pilot.click("#approval-approve")
            await pilot.pause()

            await pilot.app.push_screen(
                ApprovalDecisionModal("approval_deny", env=env),
                completed.append,
            )
            await pilot.pause()
            pilot.app.screen.query_one("#approval-reason", Input).value = "target too broad"
            await pilot.click("#approval-deny")
            await pilot.pause()

    asyncio.run(run())

    assert completed == [
        ApprovalDecisionResult(
            "Approval `approval_approve` approved; "
            "receipt `receipt_approval_approval_approve_approved` recorded."
        ),
        ApprovalDecisionResult(
            "Approval `approval_deny` denied; "
            "receipt `receipt_approval_approval_deny_denied` recorded."
        ),
    ]
    assert _approval_status(env, "approval_approve") == "resolved"
    assert _approval_status(env, "approval_deny") == "resolved"


def test_approval_decision_modal_cancel_returns_none(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _seed_approval(env, "approval_cancel")
    completed: list[ApprovalDecisionResult | None] = []

    async def run() -> None:
        class TestApp(App[None]):
            async def on_mount(self) -> None:
                self.push_screen(
                    ApprovalDecisionModal("approval_cancel", env=env),
                    completed.append,
                )

        async with TestApp().run_test() as pilot:
            await pilot.pause()
            await pilot.click("#approval-cancel")

    asyncio.run(run())

    assert completed == [None]
    assert _approval_status(env, "approval_cancel") == "open"


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def _seed_approval(env: dict[str, str], approval_id: str) -> None:
    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    try:
        open_approval_request(
            store,
            approval_id=approval_id,
            task_id=f"task_{approval_id}",
            capability="shell.execute",
            target="npm test",
            risk="runs a local command",
            policy="strict",
            requested_by="craik:runner",
            retry_path="rerun the blocked command",
            operator="operator:test",
            policy_envelope_id="strict",
            created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )
    finally:
        store.close()


def _approval_status(env: dict[str, str], approval_id: str) -> str | None:
    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    try:
        delegation = store.get_human_delegation(approval_id)
        return None if delegation is None else delegation.status
    finally:
        store.close()
