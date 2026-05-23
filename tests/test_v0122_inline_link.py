from __future__ import annotations

from craik.runtime.shell.textual_widgets.inline_link import linkify_text


def test_inline_link_wraps_http_urls() -> None:
    rendered = linkify_text("See https://example.com/docs.")

    assert "[@click=open_url('https://example.com/docs.')" in rendered
    assert "[u]https://example.com/docs.[/u]" in rendered
