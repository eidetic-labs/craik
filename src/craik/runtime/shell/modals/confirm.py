"""Reusable confirmation modal for CLI/TUI command flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


@dataclass(frozen=True, slots=True)
class ConfirmRequest:
    """Text and button labels for one confirmation prompt."""

    title: str
    message: str
    confirm_label: str = "Confirm"
    cancel_label: str = "Cancel"
    destructive: bool = False


class ConfirmModal(ModalScreen[bool]):
    """Ask the operator to confirm or decline an action."""

    supports_masked_input: ClassVar[bool] = False

    BINDINGS = [
        ("escape", "decline", "Cancel"),
        ("enter", "confirm", "Confirm"),
    ]

    def __init__(self, request: ConfirmRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        variant: Literal["primary", "error"] = "error" if self.request.destructive else "primary"
        yield Vertical(
            Label(self.request.title, classes="modal-title"),
            Static(self.request.message, classes="modal-copy"),
            Horizontal(
                Button(self.request.cancel_label, id="confirm-cancel"),
                Button(self.request.confirm_label, id="confirm-accept", variant=variant),
                classes="modal-actions",
            ),
            id="confirm-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-accept":
            self.dismiss(True)
            return
        if event.button.id == "confirm-cancel":
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_decline(self) -> None:
        self.dismiss(False)
