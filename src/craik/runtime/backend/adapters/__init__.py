"""Backend adapter seam.

Re-exports the seam foundation (``RunContext``, ``Adapter``). Concrete adapters
and the registry are intentionally NOT imported here.
"""

from craik.runtime.backend.adapters.base import (
    Adapter,
    APIAdapter,
    CLIAdapter,
    RunContext,
)

__all__ = ["APIAdapter", "Adapter", "CLIAdapter", "RunContext"]
