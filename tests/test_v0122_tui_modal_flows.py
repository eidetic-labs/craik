from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pytest import MonkeyPatch
from textual.widgets import Input

from craik.runtime.auth.guided_setup import guided_provider_defaults
from craik.runtime.auth.login import AuthCaptureResult
from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.paths import ensure_craik_home
from craik.runtime.reviewing.approvals import open_approval_request
from craik.runtime.shell.credential_storage import CredentialStorageStatus
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_modals import (
    ApprovalDecisionModal,
    AuthCaptureModal,
    AuthLogoutModal,
)
from craik.runtime.shell.textual_widgets.craik_input import CraikInput
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def test_auth_login_slash_opens_capture_modal(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            await pilot.press("/", "a", "u", "t", "h", " ", "l", "o", "g", "i", "n")
            await pilot.press(" ", "o", "p", "e", "n", "a", "i", "enter")

            assert isinstance(pilot.app.screen, AuthCaptureModal)

    asyncio.run(run())


def test_auth_capture_modal_redacts_secret_from_result(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}

    def _capture(provider: str, *, credential: str, **kwargs: object) -> AuthCaptureResult:
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
        return AuthCaptureResult(
            provider=provider,
            profile=profile,
            status=CredentialStatus(status="ok"),
            credential_storage=CredentialStorageStatus(
                backend="test",
                status="available",
                secure=True,
            ),
        )

    monkeypatch.setattr("craik.runtime.shell.textual_modals.capture_and_cache_login", _capture)

    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            await pilot.app.push_screen(AuthCaptureModal("openai", env=_env(tmp_path)))
            await pilot.pause()
            pilot.app.screen.query_one("#auth-secret", Input).value = "provider-secret"
            await pilot.click("#auth-save")
            await pilot.pause()

            assert captured == {"provider": "openai", "credential": "provider-secret"}

    asyncio.run(run())


def test_auth_logout_slash_opens_confirmation_modal(tmp_path: Path) -> None:
    async def run() -> None:
        async with CraikApp(env=_env(tmp_path)).run_test() as pilot:
            pilot.app.query_one("#input", CraikInput).value = "/auth logout openai:default"
            await pilot.press("enter")

            assert isinstance(pilot.app.screen, AuthLogoutModal)

    asyncio.run(run())


def test_approval_decide_slash_opens_decision_modal(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = _seed_approval(Path(env["CRAIK_HOME"]))
    store.close()

    async def run() -> None:
        async with CraikApp(env=env).run_test() as pilot:
            pilot.app.query_one("#input", CraikInput).value = "/approvals decide approval_shell"
            await pilot.press("enter")

            assert isinstance(pilot.app.screen, ApprovalDecisionModal)

    asyncio.run(run())


def test_approval_decision_modal_resolves_open_request(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = _seed_approval(Path(env["CRAIK_HOME"]))
    store.close()

    async def run() -> None:
        async with CraikApp(env=env).run_test() as pilot:
            await pilot.app.push_screen(ApprovalDecisionModal("approval_shell", env=env))
            await pilot.pause()
            pilot.app.screen.query_one("#approval-reason", Input).value = "scope is bounded"
            await pilot.click("#approval-approve")
            await pilot.pause()

    asyncio.run(run())

    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    try:
        delegation = store.get_human_delegation("approval_shell")
        receipts = store.list_receipts()
    finally:
        store.close()
    assert delegation is not None
    assert delegation.status == "resolved"
    assert receipts[0].redacted is True


def _seed_approval(home: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    store.initialize()
    open_approval_request(
        store,
        approval_id="approval_shell",
        task_id="task_shell",
        capability="shell.execute",
        target="npm test",
        risk="runs a local command",
        policy="strict",
        requested_by="craik:runner",
        retry_path="rerun the blocked command",
        operator="operator:test",
        policy_envelope_id="strict",
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
    )
    return store
