"""Textual app modal-flow routing helpers."""

from __future__ import annotations

from typing import Any

from craik.runtime.shell.modals.approval_decision import (
    ApprovalDecisionModal,
    ApprovalDecisionResult,
)
from craik.runtime.shell.modals.auth_capture import (
    AuthCaptureModal,
    AuthCaptureRequest,
    AuthCaptureResult,
)
from craik.runtime.shell.modals.auth_logout import (
    AuthLogoutModal,
    AuthLogoutRequest,
    AuthLogoutResult,
)
from craik.runtime.shell.modals.receipt_detail import ReceiptDetailModal
from craik.runtime.shell.textual_widgets.inline_link import linkify_text


def open_textual_modal_flow(app: Any, text: str) -> bool:
    """Open a modal-backed flow for slash commands that need direct TUI input."""
    tokens = text.split()
    if not tokens:
        return False
    if tokens[:2] in (["/auth", "login"], ["/provider", "login"]):
        provider = tokens[2] if len(tokens) > 2 else "openai"
        app.push_screen(
            AuthCaptureModal(AuthCaptureRequest(provider=provider, env=app.env)),
            lambda result: _auth_capture_complete(app, result),
        )
        return True
    if tokens[:2] == ["/auth", "logout"] or tokens[0] == "/logout":
        profile = tokens[2] if len(tokens) > 2 else app._active_profile()
        if tokens[0] == "/logout":
            profile = tokens[1] if len(tokens) > 1 else app._active_profile()
        app.push_screen(
            AuthLogoutModal(AuthLogoutRequest(profile_id=profile, env=app.env)),
            lambda result: _auth_logout_complete(app, result),
        )
        return True
    if len(tokens) >= 3 and tokens[:2] == ["/approvals", "decide"]:
        app.push_screen(
            ApprovalDecisionModal(tokens[2], env=app.env),
            lambda result: _modal_complete(app, result),
        )
        return True
    if len(tokens) >= 3 and tokens[:2] == ["/receipts", "detail"]:
        app.push_screen(ReceiptDetailModal(tokens[2], env=app.env))
        return True
    return False


def _modal_complete(app: Any, result: ApprovalDecisionResult | None) -> None:
    if result is None:
        return
    app._write_transcript(linkify_text(result.message), plain_text=result.message)
    if result.severity != "information":
        app.notify(result.message, severity=result.severity, timeout=8)


def _auth_capture_complete(app: Any, result: AuthCaptureResult | None) -> None:
    if result is None:
        return
    if result.message:
        app._write_transcript(linkify_text(result.message), plain_text=result.message)
    if result.severity != "information":
        app.notify(
            result.message or "Auth capture failed.",
            severity=result.severity,
            timeout=8,
        )
    if result.saved:
        app._refresh_status_bar()


def _auth_logout_complete(app: Any, result: AuthLogoutResult | None) -> None:
    if result is None:
        return
    if result.message:
        app._write_transcript(linkify_text(result.message), plain_text=result.message)
    if result.severity != "information":
        app.notify(result.message or "Logout failed.", severity=result.severity, timeout=8)
    if result.removed:
        app._refresh_status_bar()
