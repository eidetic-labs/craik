from __future__ import annotations

import asyncio
from collections.abc import Iterable

from textual.app import App, ComposeResult

from craik.runtime.shell.confirmations import resolve_inline_action
from craik.runtime.shell.slash_command_schema import ActionKeySet
from craik.runtime.shell.textual_widgets.inline_action_table import InlineActionTable


def test_inline_action_table_maps_canonical_keys() -> None:
    table = InlineActionTable(
        action_keys=ActionKeySet(
            enter="details",
            D="delete",
            R="rename",
            A="approve",
            F="filter",
            escape="cancel",
            **{"/": "focus-search"},
        ),
        rows=[{"id": "receipt_1", "status": "passed"}],
    )

    assert table.action_for_key("enter") == "details"
    assert table.action_for_key("D") == "delete"
    assert table.action_for_key("/") == "focus-search"
    assert table.action_for_key("escape") == "cancel"
    assert table.action_for_key("x") is None


def test_inline_action_table_dispatches_delete_on_d_key() -> None:
    async def run() -> None:
        host = _InlineActionHost(bindings=ActionKeySet(D="delete"))
        async with host.run_test() as pilot:
            await pilot.press("d")

        assert len(host.posted) == 1
        assert host.posted[0].action == "delete"
        assert host.posted[0].command_name == "/agent list"
        assert host.posted[0].row_id == "agent-1"
        assert host.table.action_log == ["delete"]

    asyncio.run(run())


def test_inline_action_table_dispatches_rename_on_r_key() -> None:
    async def run() -> None:
        host = _InlineActionHost(bindings=ActionKeySet(R="rename"))
        async with host.run_test() as pilot:
            await pilot.press("r")

        assert len(host.posted) == 1
        assert host.posted[0].action == "rename"
        assert host.posted[0].row_id == "agent-1"

    asyncio.run(run())


def test_inline_action_table_dispatches_focus_search_on_slash_key() -> None:
    async def run() -> None:
        host = _InlineActionHost(bindings=ActionKeySet(**{"/": "focus-search"}))
        async with host.run_test() as pilot:
            await pilot.press("/")

        assert len(host.posted) == 1
        assert host.posted[0].action == "focus-search"

    asyncio.run(run())


def test_inline_action_table_ignores_unmapped_escape_key() -> None:
    async def run() -> None:
        host = _InlineActionHost(bindings=ActionKeySet(D="delete"))
        async with host.run_test() as pilot:
            await pilot.press("escape")

        assert host.posted == []
        assert host.table.action_log == []

    asyncio.run(run())


def test_resolve_inline_action_maps_destructive_rows_to_slash_commands() -> None:
    cases: Iterable[tuple[str, str, str]] = (
        ("/agent list", "agent-1", "/agent delete agent-1"),
        ("/session list", "session-1", "/session delete session-1"),
        ("/receipts list", "receipt-1", "/receipts purge receipt-1"),
    )
    for command_name, row_id, command_text in cases:
        action = resolve_inline_action(command_name, "delete", row_id)

        assert action is not None
        assert action.command_text == command_text
        assert action.requires_confirmation


class _InlineActionHost(App[None]):
    def __init__(self, *, bindings: ActionKeySet) -> None:
        super().__init__()
        self.posted: list[InlineActionTable.InlineActionRequested] = []
        self.table = InlineActionTable(
            action_keys=bindings,
            rows=[{"agent_id": "agent-1", "name": "alpha"}],
            command_name="/agent list",
            row_id_field="agent_id",
            id="table",
        )

    def compose(self) -> ComposeResult:
        yield self.table

    def on_mount(self) -> None:
        self.table.focus()

    def on_inline_action_table_inline_action_requested(
        self,
        message: InlineActionTable.InlineActionRequested,
    ) -> None:
        self.posted.append(message)
