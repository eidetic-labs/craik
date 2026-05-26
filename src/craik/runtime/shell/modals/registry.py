"""Modal registry and resolution helpers for command metadata guards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from textual.screen import ModalScreen

from craik.runtime.shell.modals.auth_capture import AuthCaptureModal
from craik.runtime.shell.modals.auth_logout import AuthLogoutModal
from craik.runtime.shell.modals.confirm import ConfirmModal
from craik.runtime.shell.modals.file_picker import FilePickerModal
from craik.runtime.shell.modals.multiline_input import MultilineInputModal
from craik.runtime.shell.modals.receipt_detail import ReceiptDetailModal
from craik.runtime.shell.modals.record_display import RecordDisplayModal
from craik.runtime.shell.modals.select_choice import SelectChoiceModal
from craik.runtime.shell.modals.text_input import TextInputModal

type ModalClass = type[ModalScreen[Any]]

_CANONICAL_MODALS: dict[str, ModalClass] = {
    "ConfirmModal": ConfirmModal,
    "TextInputModal": TextInputModal,
    "SelectChoiceModal": SelectChoiceModal,
    "MultilineInputModal": MultilineInputModal,
    "FilePickerModal": FilePickerModal,
    "RecordDisplayModal": RecordDisplayModal,
    "AuthCaptureModal": AuthCaptureModal,
    "AuthLogoutModal": AuthLogoutModal,
    "ReceiptDetailModal": ReceiptDetailModal,
}

def canonical_modal_registry() -> Mapping[str, ModalClass]:
    """Return canonical modal names plus stable lowercase aliases."""
    registry: dict[str, ModalClass] = {}
    for name, modal_class in _CANONICAL_MODALS.items():
        registry[name] = modal_class
        registry[name.removesuffix("Modal")] = modal_class
        registry[_camel_to_snake(name)] = modal_class
        registry[_camel_to_snake(name.removesuffix("Modal"))] = modal_class
    return registry


def resolve_modal_class(
    name: str,
    registry: Mapping[str, ModalClass] | None = None,
) -> ModalClass | None:
    """Resolve a decorator modal target to a ModalScreen subclass."""
    return (registry or canonical_modal_registry()).get(name)


def modal_supports_secret_capture(modal_class: ModalClass) -> bool:
    """Return whether a modal can capture sensitive text without echoing it."""
    return bool(cast(object, getattr(modal_class, "supports_masked_input", False)))


def _camel_to_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)
