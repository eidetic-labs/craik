"""Canonical modal screens used by CLI/TUI command metadata."""

from __future__ import annotations

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
from craik.runtime.shell.modals.confirm import ConfirmModal, ConfirmRequest
from craik.runtime.shell.modals.file_picker import FilePickerModal, FilePickerRequest
from craik.runtime.shell.modals.multiline_input import (
    MultilineInputModal,
    MultilineInputRequest,
)
from craik.runtime.shell.modals.receipt_detail import ReceiptDetailModal
from craik.runtime.shell.modals.record_display import RecordDisplayModal, RecordDisplayRequest
from craik.runtime.shell.modals.registry import (
    ModalClass,
    canonical_modal_registry,
    modal_supports_secret_capture,
    resolve_modal_class,
)
from craik.runtime.shell.modals.select_choice import Choice, SelectChoiceModal, SelectChoiceRequest
from craik.runtime.shell.modals.text_input import TextInputModal, TextInputRequest

__all__ = [
    "AuthCaptureModal",
    "AuthCaptureRequest",
    "AuthCaptureResult",
    "AuthLogoutModal",
    "AuthLogoutRequest",
    "AuthLogoutResult",
    "ApprovalDecisionModal",
    "ApprovalDecisionResult",
    "Choice",
    "ConfirmModal",
    "ConfirmRequest",
    "FilePickerModal",
    "FilePickerRequest",
    "ModalClass",
    "MultilineInputModal",
    "MultilineInputRequest",
    "RecordDisplayModal",
    "RecordDisplayRequest",
    "ReceiptDetailModal",
    "SelectChoiceModal",
    "SelectChoiceRequest",
    "TextInputModal",
    "TextInputRequest",
    "canonical_modal_registry",
    "modal_supports_secret_capture",
    "resolve_modal_class",
]
