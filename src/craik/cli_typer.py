"""Craik Typer factory helpers."""

from __future__ import annotations

from typing import Any

import typer

from craik.runtime.cli.mistype_engine import SuggestingTyperGroup


def craik_typer(**kwargs: Any) -> typer.Typer:
    """Return a Typer app using Craik's command-suggestion group class."""
    kwargs.setdefault("cls", SuggestingTyperGroup)
    kwargs.setdefault("pretty_exceptions_show_locals", False)
    kwargs.setdefault("pretty_exceptions_short", True)
    return typer.Typer(**kwargs)
