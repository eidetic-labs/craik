"""Adapter seam foundation: `RunContext` and the `Adapter` protocol.

This module is intentionally tiny and dependency-free beyond the Phase-1 event
type. Concrete adapters (CLI / API families) live in sibling modules and are
registered through ``select_adapter``; each concrete adapter holds its own
``VendorProfile`` injected at construction by ``select_adapter`` -- the profile
is deliberately NOT part of ``RunContext``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from craik.runtime.backend.events import BackendEvent


@dataclass(frozen=True)
class RunContext:
    """Per-run inputs handed to an adapter's ``run`` method.

    ``decide`` maps a tool-request dict to ``"allow"`` / ``"deny"``. It is used
    by ``APIAdapter.tool_loop`` directly, and by the CLI hook bridge (Phase 5)
    to resolve a hook callback.
    """

    prompt: str
    env: dict[str, str]
    emit: Callable[[BackendEvent], None]
    decide: Callable[[dict[str, Any]], str]
    require_operator_approval: bool


class Adapter(Protocol):
    """Structural protocol implemented by every concrete backend adapter."""

    vendor: str  # "anthropic" | "openai" | "google"
    surface: str  # "cli" | "api"

    def supports_live_gating(self) -> bool: ...

    def run(self, ctx: RunContext) -> Iterable[BackendEvent]: ...
