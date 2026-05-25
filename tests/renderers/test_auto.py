"""Tests for renderer shape detection."""

from __future__ import annotations

from craik.runtime.shell.renderers.auto import detect_shape


def test_detect_shape_flat_dict_is_kv() -> None:
    assert detect_shape({"state": "ready", "configured": True}) == "kv"


def test_detect_shape_dict_with_small_nested_fields_is_card() -> None:
    assert detect_shape({"name": "openai", "capabilities": {"chat": True}}) == "card"


def test_detect_shape_deep_nested_dict_is_tree() -> None:
    assert detect_shape({"a": {"b": 1}, "c": {"d": 2}, "e": {"f": 3}}) == "tree"


def test_detect_shape_list_of_flat_dicts_is_table() -> None:
    assert detect_shape([{"name": "openai"}, {"name": "anthropic"}]) == "table"


def test_detect_shape_list_of_nested_dicts_is_card_list() -> None:
    assert detect_shape([{"name": "openai", "capabilities": {"chat": True}}]) == "card_list"


def test_detect_shape_markdown_string_is_markdown() -> None:
    assert detect_shape("# Title") == "markdown"
