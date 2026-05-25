"""Reusable choice-selection modal for CLI/TUI command flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static


@dataclass(frozen=True, slots=True)
class Choice:
    """One selectable value."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class SelectChoiceRequest:
    """Configuration for one select prompt."""

    title: str
    message: str
    choices: tuple[Choice, ...]
    initial_value: str | None = None
    submit_label: str = "Select"


class SelectChoiceModal(ModalScreen[str | None]):
    """Let the operator choose one value from a bounded option list."""

    supports_masked_input: ClassVar[bool] = False

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Select"),
    ]

    def __init__(self, request: SelectChoiceRequest) -> None:
        super().__init__()
        if not request.choices:
            raise ValueError("SelectChoiceModal requires at least one choice")
        self.request = request

    def compose(self) -> ComposeResult:
        options = [(choice.label, choice.value) for choice in self.request.choices]
        initial = self.request.initial_value or self.request.choices[0].value
        yield Vertical(
            Label(self.request.title, classes="modal-title"),
            Static(self.request.message, classes="modal-copy"),
            Select[str](options, value=initial, allow_blank=False, id="choice-select"),
            Horizontal(
                Button("Cancel", id="choice-cancel"),
                Button(self.request.submit_label, id="choice-submit", variant="primary"),
                classes="modal-actions",
            ),
            id="select-choice-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "choice-cancel":
            self.dismiss(None)
            return
        if event.button.id == "choice-submit":
            self._submit()

    def action_submit(self) -> None:
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        value = self.query_one("#choice-select", Select).value
        self.dismiss(str(value))
