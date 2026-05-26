"""Canonical-composed auth logout modal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from textual.screen import ModalScreen

from craik.runtime.auth.guided_setup import GUIDED_PROVIDER_DEFAULTS
from craik.runtime.auth.login import auth_status_payload, logout_provider
from craik.runtime.shell.modals.confirm import ConfirmModal, ConfirmRequest
from craik.runtime.shell.modals.select_choice import Choice, SelectChoiceModal, SelectChoiceRequest


@dataclass(frozen=True, slots=True)
class AuthLogoutRequest:
    """Operator-facing payload for one logout flow."""

    profile_id: str | None = None
    env: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class AuthLogoutResult:
    """Redacted outcome of one logout flow."""

    removed: bool
    removed_profile_id: str | None = None
    message: str | None = None
    severity: Literal["information", "warning", "error"] = "information"


class AuthLogoutModal(ModalScreen[AuthLogoutResult]):
    """Choose an auth profile and confirm removal using canonical primitives."""

    def __init__(self, request: AuthLogoutRequest) -> None:
        super().__init__()
        self.request = request
        self._profile_id = request.profile_id

    def on_mount(self) -> None:
        if self._profile_id:
            self._confirm_logout()
            return
        self._ask_profile()

    def _ask_profile(self) -> None:
        profile_ids = _visible_profile_ids(self.request.env)
        if not profile_ids:
            self.dismiss(
                AuthLogoutResult(
                    removed=False,
                    message="No auth profiles are available to remove.",
                    severity="warning",
                )
            )
            return
        self.app.push_screen(
            SelectChoiceModal(
                SelectChoiceRequest(
                    title="Remove credential profile",
                    message="Choose the auth profile to remove.",
                    choices=tuple(
                        Choice(label=profile_id, value=profile_id)
                        for profile_id in profile_ids
                    ),
                    initial_value=profile_ids[0],
                    submit_label="Continue",
                )
            ),
            self._after_profile,
        )

    def _after_profile(self, profile_id: str | None) -> None:
        if profile_id is None:
            self.dismiss(AuthLogoutResult(removed=False, message="Logout cancelled."))
            return
        self._profile_id = profile_id
        self._confirm_logout()

    def _confirm_logout(self) -> None:
        profile_id = self._profile_id or "unknown"
        self.app.push_screen(
            ConfirmModal(
                ConfirmRequest(
                    title="Remove credential profile?",
                    message=f"Remove auth profile `{profile_id}`?",
                    confirm_label="Remove",
                    destructive=True,
                )
            ),
            self._after_confirm,
        )

    def _after_confirm(self, confirmed: bool | None) -> None:
        profile_id = self._profile_id
        if not confirmed or profile_id is None:
            self.dismiss(AuthLogoutResult(removed=False, message="Logout cancelled."))
            return
        provider = _provider_from_profile_id(profile_id)
        result = logout_provider(provider, profile_id=profile_id, env=self.request.env)
        removed = bool(result["removed_profile"])
        status = "removed" if removed else "not found"
        self.dismiss(
            AuthLogoutResult(
                removed=removed,
                removed_profile_id=profile_id,
                message=f"Auth profile `{profile_id}` {status}.",
            )
        )


def _visible_profile_ids(env: dict[str, str] | None) -> list[str]:
    try:
        rows = auth_status_payload(env)
    except Exception:
        return []
    return [str(row["id"]) for row in rows if row.get("id")]


def _provider_from_profile_id(profile_id: str) -> str:
    provider = profile_id.split(":", 1)[0].strip().lower()
    return provider if provider in GUIDED_PROVIDER_DEFAULTS else "openai"
