from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.tree import Tree

from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_widgets.slash_renderers import render_slash_payload


def _render_text(renderable: object) -> str:
    console = Console(record=True, width=100)
    console.print(renderable)
    return console.export_text()


def test_table_renderer_formats_rows_without_json_wall() -> None:
    renderable = render_slash_payload(
        [
            {"provider": "openai", "model": "gpt-4o-mini", "state": "ready"},
            {"provider": "local", "model": "llama", "state": "missing"},
        ],
        shape="table",
    )

    assert isinstance(renderable, Table)
    rendered = _render_text(renderable)
    assert "provider" in rendered
    assert "gpt-4o-mini" in rendered
    assert '{"provider"' not in rendered


def test_key_value_renderer_formats_mapping() -> None:
    renderable = render_slash_payload(
        {"active_model": "openai/gpt-4o-mini", "fallbacks": []},
        shape="kv",
    )

    assert isinstance(renderable, Table)
    rendered = _render_text(renderable)
    assert "active model" in rendered
    assert "openai/gpt-4o-mini" in rendered


def test_tree_renderer_formats_nested_payload() -> None:
    renderable = render_slash_payload(
        {"readiness": {"state": "fully-ready", "missing": []}},
        shape="tree",
    )

    assert isinstance(renderable, Tree)
    rendered = _render_text(renderable)
    assert "readiness" in rendered
    assert "fully-ready" in rendered


def test_markdown_renderer_formats_text() -> None:
    renderable = render_slash_payload("# Help\n\nUse `/status`.", shape="markdown")

    assert isinstance(renderable, Markdown)
    assert "/status" in _render_text(renderable)


def test_dispatch_result_carries_structured_payload_for_textual_rendering() -> None:
    result = dispatch_slash_command("/provider")

    assert result.command_name == "provider"
    assert result.payload_shape == "table"
    assert isinstance(result.payload, list)
    assert result.text.startswith("[")
