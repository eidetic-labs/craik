"""Canonical approval-decision modal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.reviewing.approvals import (
    ApprovalDecision,
    ApprovalNotFoundError,
    ApprovalStateError,
    approval_view,
    decide_approval,
)
from craik.runtime.shell.textual_widgets.glyph_palette import REVIEW_GLYPH
from craik.runtime.store import LocalStore


@dataclass(frozen=True, slots=True)
class ApprovalDecisionResult:
    """Redacted completion result from an approval decision flow."""

    message: str
    severity: Literal["information", "warning", "error"] = "information"


class ApprovalDecisionModal(ModalScreen[ApprovalDecisionResult | None]):
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
            self.dismiss(
                ApprovalDecisionResult("Approval decision requires a reason.", "warning")
            )
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
            self.dismiss(ApprovalDecisionResult(f"Approval decision failed: {exc}", "error"))
            return
        finally:
            store.close()
        self.dismiss(
            ApprovalDecisionResult(
                f"Approval `{result.approval.id}` {decision}; "
                f"receipt `{result.receipt.id}` recorded."
            )
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
