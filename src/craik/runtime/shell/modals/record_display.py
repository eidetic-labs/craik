"""Read-only structured-record display modal."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


@dataclass(frozen=True, slots=True)
class RecordDisplayRequest:
    """Structured record and actions for read-only modal display."""

    title: str
    record: dict[str, Any]
    actions: list[str] = field(default_factory=lambda: ["close"])


class RecordDisplayModal(ModalScreen[str | None]):
    """Display a structured record and return the selected action."""

    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, request: RecordDisplayRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.request.title, classes="modal-title"),
            ScrollableContainer(
                Static(_format_record(self.request.record), id="record-body", classes="modal-copy"),
                id="record-scroll",
            ),
            Horizontal(
                *[
                    Button(_action_label(action), id=f"record-action-{action}")
                    for action in self.request.actions
                ],
                classes="modal-actions",
            ),
            id="record-display-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("record-action-"):
            self.dismiss(button_id.removeprefix("record-action-"))

    def action_close(self) -> None:
        self.dismiss(None)


def _format_record(record: dict[str, Any]) -> str:
    return escape(json.dumps(record, indent=2, sort_keys=True, default=str))


def _action_label(action: str) -> str:
    return action.replace("_", " ").strip().title() or "Action"
