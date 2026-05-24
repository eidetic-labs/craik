"""Modal screens for interactive Craik TUI flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from craik.runtime.auth.guided_setup import GUIDED_PROVIDER_DEFAULTS
from craik.runtime.auth.login import capture_and_cache_login, logout_provider
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.reviewing.approvals import (
    ApprovalDecision,
    ApprovalNotFoundError,
    ApprovalStateError,
    approval_view,
    decide_approval,
)
from craik.runtime.shell.textual_widgets.glyph_palette import RECEIPT_OK, REVIEW_GLYPH
from craik.runtime.store import LocalStore
from craik.runtime.store.receipt_integrity import contract_receipt_hmac_status


@dataclass(frozen=True)
class ModalFlowResult:
    """Redacted completion result from an interactive modal flow."""

    message: str
    severity: Literal["information", "warning", "error"] = "information"


class AuthCaptureModal(ModalScreen[ModalFlowResult | None]):
    """Capture a provider credential without echoing secret material."""

    def __init__(self, provider: str = "openai", *, env: dict[str, str] | None = None) -> None:
        super().__init__()
        self.provider = provider
        self.env = env

    def compose(self) -> ComposeResult:
        providers = [(name, name) for name in sorted(GUIDED_PROVIDER_DEFAULTS)]
        yield Vertical(
            Label("Provider credential", classes="modal-title"),
            Static("Credential material is redacted from the transcript.", classes="modal-copy"),
            Select[str](
                providers,
                value=self.provider if self.provider in GUIDED_PROVIDER_DEFAULTS else "openai",
                allow_blank=False,
                id="auth-provider",
            ),
            Input(placeholder="API key", password=True, id="auth-secret"),
            Horizontal(
                Button("Cancel", id="auth-cancel"),
                Button("Save", id="auth-save", variant="primary"),
                classes="modal-actions",
            ),
            id="auth-capture-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "auth-cancel":
            self.dismiss(None)
            return
        if event.button.id == "auth-save":
            self._save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "auth-secret":
            self._save()

    def _save(self) -> None:
        provider = str(self.query_one("#auth-provider", Select).value)
        secret = self.query_one("#auth-secret", Input).value
        if not secret.strip():
            self.dismiss(ModalFlowResult("Auth capture cancelled: credential is blank.", "warning"))
            return
        try:
            result = capture_and_cache_login(
                provider,
                credential=secret,
                allow_local_base_url=provider == "local",
                env=self.env,
            )
        except ValueError as exc:
            self.dismiss(ModalFlowResult(f"Auth capture failed for {provider}: {exc}", "error"))
            return
        if result.status.status != "ok":
            detail = f": {result.status.detail}" if result.status.detail else ""
            self.dismiss(
                ModalFlowResult(
                    f"Auth capture rejected for {provider}{detail}",
                    "warning",
                )
            )
            return
        warning = f" Warning: {result.warning}" if result.warning else ""
        self.dismiss(
            ModalFlowResult(
                f"Auth profile `{result.profile.id}` saved for {provider}.{warning}",
            )
        )


class AuthLogoutModal(ModalScreen[ModalFlowResult | None]):
    """Confirm auth profile logout before removing cached credentials."""

    def __init__(self, profile_id: str, *, env: dict[str, str] | None = None) -> None:
        super().__init__()
        self.profile_id = profile_id
        self.env = env

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Remove credential profile?", classes="modal-title"),
            Static(f"Profile: {escape(self.profile_id)}", classes="modal-copy"),
            Horizontal(
                Button("Cancel", id="logout-cancel"),
                Button("Remove", id="logout-confirm", variant="error"),
                classes="modal-actions",
            ),
            id="auth-logout-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "logout-cancel":
            self.dismiss(None)
            return
        if event.button.id == "logout-confirm":
            provider = _provider_from_profile_id(self.profile_id)
            result = logout_provider(provider, profile_id=self.profile_id, env=self.env)
            removed = "removed" if result["removed_profile"] else "not found"
            self.dismiss(ModalFlowResult(f"Auth profile `{self.profile_id}` {removed}."))


class ApprovalDecisionModal(ModalScreen[ModalFlowResult | None]):
    """Review and resolve one open approval request."""

    def __init__(self, approval_id: str, *, env: dict[str, str] | None = None) -> None:
        super().__init__()
        self.approval_id = approval_id
        self.env = env

    def compose(self) -> ComposeResult:
        summary = self._approval_summary()
        yield Vertical(
            Label(f"{REVIEW_GLYPH} Approval decision", classes="modal-title"),
            Static(summary, id="approval-summary", classes="modal-copy"),
            Input(placeholder="Reason", id="approval-reason"),
            Horizontal(
                Button("Cancel", id="approval-cancel"),
                Button("Deny", id="approval-deny", variant="error"),
                Button("Approve", id="approval-approve", variant="success"),
                classes="modal-actions",
            ),
            id="approval-decision-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approval-cancel":
            self.dismiss(None)
            return
        if event.button.id == "approval-deny":
            self._decide("denied")
            return
        if event.button.id == "approval-approve":
            self._decide("approved")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "approval-reason":
            self._decide("approved")

    def _approval_summary(self) -> str:
        store = _open_store(self.env)
        try:
            delegation = store.get_human_delegation(self.approval_id)
            if delegation is None or delegation.kind != "approval":
                return f"Approval `{escape(self.approval_id)}` was not found."
            view = approval_view(delegation)
        finally:
            store.close()
        return (
            f"ID: {view.id}\n"
            f"Capability: {escape(view.capability)}\n"
            f"Target: {escape(view.target)}\n"
            f"Risk: {escape(view.risk)}\n"
            f"Policy: {escape(view.policy)}\n"
            f"Retry: {escape(view.retry_path)}"
        )

    def _decide(self, decision: ApprovalDecision) -> None:
        reason = self.query_one("#approval-reason", Input).value.strip()
        if not reason:
            self.dismiss(ModalFlowResult("Approval decision requires a reason.", "warning"))
            return
        store = _open_store(self.env)
        try:
            operator = _operator_subject(self.env)
            result = decide_approval(
                store,
                self.approval_id,
                decision=decision,
                operator=operator,
                reason=reason,
            )
        except (ApprovalNotFoundError, ApprovalStateError) as exc:
            self.dismiss(ModalFlowResult(f"Approval decision failed: {exc}", "error"))
            return
        finally:
            store.close()
        self.dismiss(
            ModalFlowResult(
                f"Approval `{result.approval.id}` {decision}; "
                f"receipt `{result.receipt.id}` recorded."
            )
        )


class ReceiptDetailModal(ModalScreen[None]):
    """Show audit details for one receipt id."""

    def __init__(self, receipt_id: str, *, env: dict[str, str] | None = None) -> None:
        super().__init__()
        self.receipt_id = receipt_id
        self.env = env

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"{RECEIPT_OK} Receipt details", classes="modal-title"),
            Static(self._detail_text(), id="receipt-detail", classes="modal-copy"),
            Horizontal(
                Button("Close", id="receipt-close", variant="primary"),
                classes="modal-actions",
            ),
            id="receipt-detail-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "receipt-close":
            self.dismiss(None)

    def _detail_text(self) -> str:
        store = _open_store(self.env)
        try:
            receipt = _find_receipt(store, self.receipt_id)
            if receipt is None:
                return f"Receipt `{escape(self.receipt_id)}` was not found."
            integrity_status = _receipt_integrity_status(store, receipt)
        finally:
            store.close()
        result = getattr(receipt, "result", None)
        status = getattr(result, "status", "unknown")
        summary = getattr(result, "summary", "")
        return (
            f"ID: {escape(self.receipt_id)}\n"
            f"Integrity: {escape(integrity_status)}\n"
            f"Status: {escape(str(status))}\n"
            f"Summary: {escape(str(summary or 'not recorded'))}"
        )


def _open_store(env: dict[str, str] | None) -> LocalStore:
    paths = resolve_craik_paths(env)
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _operator_subject(env: dict[str, str] | None) -> str:
    try:
        return OperatorSessionStore.from_env(env).get().subject
    except OperatorSessionNotFoundError:
        return "operator:local"


def _provider_from_profile_id(profile_id: str) -> str:
    provider = profile_id.split(":", 1)[0].strip().lower()
    return provider if provider in GUIDED_PROVIDER_DEFAULTS else "openai"


def _find_receipt(store: LocalStore, receipt_id: str) -> object | None:
    for method_name in ("list_receipts", "list_plugin_receipts", "list_gateway_receipts"):
        method = getattr(store, method_name, None)
        if method is None:
            continue
        for receipt in method():
            if getattr(receipt, "id", None) == receipt_id:
                return cast(object, receipt)
    return None


def _receipt_integrity_status(store: LocalStore, receipt: object) -> str:
    hmac = getattr(receipt, "receipt_hmac", None)
    if hmac:
        try:
            return f"{contract_receipt_hmac_status(store, receipt)} hmac"  # type: ignore[arg-type]
        except (AttributeError, TypeError, ValueError):
            return "tampered hmac"
    receipt_hash = getattr(receipt, "self_hash", None)
    if receipt_hash:
        return "verified receipt chain"
    return "unverified"
