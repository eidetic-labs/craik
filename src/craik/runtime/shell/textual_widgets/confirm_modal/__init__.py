"""Confirmation modal for destructive slash-command actions."""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from craik.runtime.shell.textual_widgets.glyph_palette import WARN_GLYPH


@dataclass(frozen=True)
class ConfirmationRequest:
    """Confirmation metadata for one destructive slash-command action."""

    command_text: str
    title: str
    message: str
    confirm_label: str = "Yes"
    cancel_label: str = "No"
    destructive: bool = True


class ConfirmModal(ModalScreen[bool]):
    """Ask the operator to confirm or decline a destructive command."""

    BINDINGS = [
        ("escape", "decline", "Cancel"),
        ("enter", "confirm", "Confirm"),
    ]

    def __init__(self, request: ConfirmationRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"{WARN_GLYPH} {self.request.title}", classes="modal-title"),
            Static(self.request.message, classes="modal-copy"),
            Horizontal(
                Button(self.request.cancel_label, id="confirm-no"),
                Button(
                    self.request.confirm_label,
                    id="confirm-yes",
                    variant="error" if self.request.destructive else "primary",
                ),
                classes="modal-actions",
            ),
            id="confirm-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(True)
            return
        if event.button.id == "confirm-no":
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_decline(self) -> None:
        self.dismiss(False)
