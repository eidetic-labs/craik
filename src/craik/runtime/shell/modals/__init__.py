"""Canonical modal screens used by CLI/TUI command metadata."""

from __future__ import annotations

from craik.runtime.shell.modals.confirm import ConfirmModal, ConfirmRequest
from craik.runtime.shell.modals.file_picker import FilePickerModal, FilePickerRequest
from craik.runtime.shell.modals.multiline_input import (
    MultilineInputModal,
    MultilineInputRequest,
)
from craik.runtime.shell.modals.registry import (
    CANONICAL_MODAL_NAMES,
    ModalClass,
    canonical_modal_registry,
    modal_supports_secret_capture,
    resolve_modal_class,
)
from craik.runtime.shell.modals.select_choice import Choice, SelectChoiceModal, SelectChoiceRequest
from craik.runtime.shell.modals.text_input import TextInputModal, TextInputRequest

__all__ = [
    "CANONICAL_MODAL_NAMES",
    "Choice",
    "ConfirmModal",
    "ConfirmRequest",
    "FilePickerModal",
    "FilePickerRequest",
    "ModalClass",
    "MultilineInputModal",
    "MultilineInputRequest",
    "SelectChoiceModal",
    "SelectChoiceRequest",
    "TextInputModal",
    "TextInputRequest",
    "canonical_modal_registry",
    "modal_supports_secret_capture",
    "resolve_modal_class",
]
