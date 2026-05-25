"""Output context for CLI/TUI shared command callbacks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_SLASH_DISPATCH_ACTIVE: ContextVar[bool] = ContextVar(
    "craik_slash_dispatch_active",
    default=False,
)


def slash_dispatch_active() -> bool:
    """Return whether a command callback is running under slash dispatch."""
    return _SLASH_DISPATCH_ACTIVE.get()


@contextmanager
def slash_dispatch_context() -> Iterator[None]:
    """Mark shared command callbacks as running from the slash dispatcher."""
    token = _SLASH_DISPATCH_ACTIVE.set(True)
    try:
        yield
    finally:
        _SLASH_DISPATCH_ACTIVE.reset(token)
