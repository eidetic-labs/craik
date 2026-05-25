"""Tests for renderer helper modules."""

from __future__ import annotations

from craik.runtime.shell.renderers.nested_summary import summarize_nested
from craik.runtime.shell.renderers.status_icons import (
    STATUS_FAIL,
    STATUS_OK,
    STATUS_PENDING,
    STATUS_WARN,
    icon_for_bool,
    icon_for_status,
)
from craik.runtime.shell.renderers.width_budget import (
    budget_columns,
    truncate_to_width,
)


def test_status_icons_for_booleans() -> None:
    assert icon_for_bool(True) == STATUS_OK
    assert icon_for_bool(False) == STATUS_FAIL


def test_status_icons_for_named_status() -> None:
    assert icon_for_status("configured") == STATUS_OK
    assert icon_for_status("missing") == STATUS_FAIL
    assert icon_for_status("pending") == STATUS_PENDING
    assert icon_for_status("warning") == STATUS_WARN


def test_width_budget_equal_distribution() -> None:
    columns = budget_columns(num_columns=4, terminal_width=80, min_width=8)

    assert sum(columns) <= 80
    assert len(columns) == 4
    assert all(column >= 8 for column in columns)


def test_width_budget_drops_columns_when_too_narrow() -> None:
    columns = budget_columns(num_columns=20, terminal_width=60, min_width=8)

    assert len(columns) < 20
    assert all(column == 8 for column in columns)


def test_width_budget_handles_no_columns() -> None:
    assert budget_columns(num_columns=0, terminal_width=80) == []


def test_truncate_to_width_short_string() -> None:
    assert truncate_to_width("hello", 10) == "hello"


def test_truncate_to_width_long_string() -> None:
    result = truncate_to_width("hello world this is long", 10)

    assert len(result) == 10
    assert result.endswith("…")


def test_truncate_to_width_zero_width() -> None:
    assert truncate_to_width("hello", 0) == ""


def test_summarize_nested_dict() -> None:
    payload = {"a": 1, "b": 2, "c": 3, "d": 4}
    summary = summarize_nested(payload, item_name="keys")

    assert "4 keys" in summary


def test_summarize_nested_list() -> None:
    summary = summarize_nested([1, 2, 3, 4, 5], item_name="items")

    assert "5 items" in summary


def test_summarize_nested_preserves_first_few_names() -> None:
    payload = {"chat": True, "tools": True, "vision": True, "images": True}
    summary = summarize_nested(payload, item_name="capabilities", show_first=3)

    assert "chat" in summary
    assert "tools" in summary
    assert "vision" in summary
    assert "..." in summary
