"""Canonical-composed provider credential capture modal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from textual.screen import ModalScreen

from craik.runtime.auth.guided_setup import GUIDED_PROVIDER_DEFAULTS
from craik.runtime.auth.login import capture_and_cache_login
from craik.runtime.shell.modals.confirm import ConfirmModal, ConfirmRequest
from craik.runtime.shell.modals.select_choice import Choice, SelectChoiceModal, SelectChoiceRequest
from craik.runtime.shell.modals.text_input import TextInputModal, TextInputRequest

CredentialKind = Literal["api_key"]


@dataclass(frozen=True, slots=True)
class AuthCaptureRequest:
    """Operator-facing payload for one credential capture flow."""

    provider: str = "openai"
    env: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class AuthCaptureResult:
    """Redacted outcome of a credential capture flow."""

    provider: str
    saved: bool
    credential_kind: CredentialKind | None = None
    profile_id: str | None = None
    message: str | None = None
    severity: Literal["information", "warning", "error"] = "information"


class AuthCaptureModal(ModalScreen[AuthCaptureResult]):
    """Capture a provider credential by composing canonical primitive modals."""

    def __init__(self, request: AuthCaptureRequest) -> None:
        super().__init__()
        self.request = request
        self._provider = _safe_provider(request.provider)
        self._credential_kind: CredentialKind = "api_key"
        self._credential: str | None = None

    def on_mount(self) -> None:
        self._ask_provider()

    def _ask_provider(self) -> None:
        choices = tuple(
            Choice(label=name, value=name) for name in sorted(GUIDED_PROVIDER_DEFAULTS)
        )
        self.app.push_screen(
            SelectChoiceModal(
                SelectChoiceRequest(
                    title="Provider credential",
                    message="Choose the provider for this credential.",
                    choices=choices,
                    initial_value=self._provider,
                    submit_label="Continue",
                )
            ),
            self._after_provider,
        )

    def _after_provider(self, provider: str | None) -> None:
        if provider is None:
            self._cancel("Auth capture cancelled.")
            return
        self._provider = _safe_provider(provider)
        self._ask_credential()

    def _ask_credential(self) -> None:
        self.app.push_screen(
            TextInputModal(
                TextInputRequest(
                    title=f"Enter {self._provider} API key",
                    message="Credential material is redacted from the transcript.",
                    placeholder="API key",
                    submit_label="Continue",
                    masked=True,
                    required=True,
                )
            ),
            self._after_credential,
        )

    def _after_credential(self, credential: str | None) -> None:
        if not credential or not credential.strip():
            self._cancel("Auth capture cancelled: credential is blank.", severity="warning")
            return
        self._credential = credential
        self._confirm_save()

    def _confirm_save(self) -> None:
        self.app.push_screen(
            ConfirmModal(
                ConfirmRequest(
                    title="Save credential?",
                    message=f"Save this API key for {self._provider}?",
                    confirm_label="Save",
                    destructive=False,
                )
            ),
            self._after_confirm,
        )

    def _after_confirm(self, confirmed: bool | None) -> None:
        if not confirmed:
            self._cancel("Auth capture cancelled.")
            return
        credential = self._credential
        if credential is None:
            self._cancel("Auth capture cancelled: credential is blank.", severity="warning")
            return
        try:
            result = capture_and_cache_login(
                self._provider,
                credential=credential,
                allow_local_base_url=self._provider == "local",
                env=self.request.env,
            )
        except ValueError as exc:
            self.dismiss(
                AuthCaptureResult(
                    provider=self._provider,
                    saved=False,
                    credential_kind=self._credential_kind,
                    message=f"Auth capture failed for {self._provider}: {exc}",
                    severity="error",
                )
            )
            return
        if result.status.status != "ok":
            detail = f": {result.status.detail}" if result.status.detail else ""
            self.dismiss(
                AuthCaptureResult(
                    provider=self._provider,
                    saved=False,
                    credential_kind=self._credential_kind,
                    profile_id=result.profile.id,
                    message=f"Auth capture rejected for {self._provider}{detail}",
                    severity="warning",
                )
            )
            return
        warning = f" Warning: {result.warning}" if result.warning else ""
        self.dismiss(
            AuthCaptureResult(
                provider=self._provider,
                saved=True,
                credential_kind=self._credential_kind,
                profile_id=result.profile.id,
                message=f"Auth profile `{result.profile.id}` saved for {self._provider}.{warning}",
            )
        )

    def _cancel(
        self,
        message: str,
        *,
        severity: Literal["information", "warning", "error"] = "information",
    ) -> None:
        self.dismiss(
            AuthCaptureResult(
                provider=self._provider,
                saved=False,
                credential_kind=self._credential_kind,
                message=message,
                severity=severity,
            )
        )


def _safe_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    return normalized if normalized in GUIDED_PROVIDER_DEFAULTS else "openai"
