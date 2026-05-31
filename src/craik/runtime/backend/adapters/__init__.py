"""Backend adapter seam.

Re-exports the seam foundation (``RunContext``, ``Adapter``) and the dispatch
entry point ``select_adapter``. The concrete stub classes live in
``adapters.concrete`` and are reachable through ``select_adapter``.
"""

from craik.runtime.backend.adapters.base import (
    Adapter,
    APIAdapter,
    CLIAdapter,
    RunContext,
)
from craik.runtime.backend.adapters.registry import select_adapter

__all__ = [
    "APIAdapter",
    "Adapter",
    "CLIAdapter",
    "RunContext",
    "select_adapter",
]
