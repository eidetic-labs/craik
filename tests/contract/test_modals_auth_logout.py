"""Smoke tests for canonical-composed auth logout modal."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pytest import MonkeyPatch
from textual.app import App

from craik.runtime.shell.modals.auth_logout import (
    AuthLogoutModal,
    AuthLogoutRequest,
    AuthLogoutResult,
)


def test_auth_logout_selects_profile_and_confirms(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    completed: list[AuthLogoutResult] = []
    removed: dict[str, str] = {}

    monkeypatch.setattr(
        "craik.runtime.shell.modals.auth_logout.auth_status_payload",
        lambda env: [{"id": "openai:default"}],
    )

    def _logout(provider: str, *, profile_id: str | None, **kwargs: object) -> dict[str, object]:
        removed["provider"] = provider
        removed["profile_id"] = profile_id or ""
        return {
            "provider": provider,
            "profile_id": profile_id,
            "removed_profile": True,
            "removed_keyring_ref": True,
            "redacted": True,
        }

    monkeypatch.setattr("craik.runtime.shell.modals.auth_logout.logout_provider", _logout)

    async def run() -> None:
        class TestApp(App[None]):
            async def on_mount(self) -> None:
                self.push_screen(
                    AuthLogoutModal(
                        AuthLogoutRequest(env={"CRAIK_HOME": str(tmp_path / ".craik")})
                    ),
                    completed.append,
                )

        async with TestApp().run_test() as pilot:
            await pilot.pause()
            await pilot.click("#choice-submit")
            await pilot.pause()
            await pilot.click("#confirm-accept")

    asyncio.run(run())

    assert removed == {"provider": "openai", "profile_id": "openai:default"}
    assert completed == [
        AuthLogoutResult(
            removed=True,
            removed_profile_id="openai:default",
            message="Auth profile `openai:default` removed.",
        )
    ]


def test_auth_logout_cancel_at_profile_selection(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    completed: list[AuthLogoutResult] = []
    monkeypatch.setattr(
        "craik.runtime.shell.modals.auth_logout.auth_status_payload",
        lambda env: [{"id": "openai:default"}],
    )

    async def run() -> None:
        class TestApp(App[None]):
            async def on_mount(self) -> None:
                self.push_screen(
                    AuthLogoutModal(
                        AuthLogoutRequest(env={"CRAIK_HOME": str(tmp_path / ".craik")})
                    ),
                    completed.append,
                )

        async with TestApp().run_test() as pilot:
            await pilot.pause()
            await pilot.press("escape")

    asyncio.run(run())

    assert completed == [AuthLogoutResult(removed=False, message="Logout cancelled.")]
