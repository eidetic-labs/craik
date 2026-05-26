"""Smoke tests for canonical-composed auth capture modal."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pytest import MonkeyPatch
from textual.app import App
from textual.widgets import Input

from craik.runtime.auth.guided_setup import guided_provider_defaults
from craik.runtime.auth.login import AuthCaptureResult as LoginCaptureResult
from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.shell.credential_storage import CredentialStorageStatus
from craik.runtime.shell.modals.auth_capture import (
    AuthCaptureModal,
    AuthCaptureRequest,
    AuthCaptureResult,
)


def test_auth_capture_full_flow_api_key(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    completed: list[AuthCaptureResult] = []
    captured: dict[str, str] = {}

    def _capture(provider: str, *, credential: str, **kwargs: object) -> LoginCaptureResult:
        captured["provider"] = provider
        captured["credential"] = credential
        defaults = guided_provider_defaults(provider)
        profile = AuthProfile(
            id=str(defaults["profile_id"]),
            kind=CredentialKind.KEYRING_REF,
            provider_family=defaults["family"],
            metadata={"ref": "redacted"},
            created_at=datetime.now(UTC),
        )
        return LoginCaptureResult(
            provider=provider,
            profile=profile,
            status=CredentialStatus(status="ok"),
            credential_storage=CredentialStorageStatus(
                backend="test",
                status="available",
                secure=True,
            ),
        )

    monkeypatch.setattr("craik.runtime.shell.modals.auth_capture.capture_and_cache_login", _capture)

    async def run() -> None:
        class TestApp(App[None]):
            async def on_mount(self) -> None:
                self.push_screen(
                    AuthCaptureModal(
                        AuthCaptureRequest(
                            provider="openai",
                            env={"CRAIK_HOME": str(tmp_path / ".craik")},
                        )
                    ),
                    completed.append,
                )

        async with TestApp().run_test() as pilot:
            await pilot.pause()
            await pilot.click("#choice-submit")
            await pilot.pause()
            pilot.app.screen.query_one("#text-input", Input).value = "provider-key"
            await pilot.click("#text-submit")
            await pilot.pause()
            await pilot.click("#confirm-accept")

    asyncio.run(run())

    assert captured == {"provider": "openai", "credential": "provider-key"}
    assert completed == [
        AuthCaptureResult(
            provider="openai",
            saved=True,
            credential_kind="api_key",
            profile_id="openai:default",
            message="Auth profile `openai:default` saved for openai.",
        )
    ]


def test_auth_capture_cancel_at_provider_selection(tmp_path: Path) -> None:
    completed: list[AuthCaptureResult] = []

    async def run() -> None:
        class TestApp(App[None]):
            async def on_mount(self) -> None:
                self.push_screen(
                    AuthCaptureModal(
                        AuthCaptureRequest(
                            provider="openai",
                            env={"CRAIK_HOME": str(tmp_path / ".craik")},
                        )
                    ),
                    completed.append,
                )

        async with TestApp().run_test() as pilot:
            await pilot.pause()
            await pilot.press("escape")

    asyncio.run(run())

    assert completed == [
        AuthCaptureResult(
            provider="openai",
            saved=False,
            credential_kind="api_key",
            message="Auth capture cancelled.",
        )
    ]
