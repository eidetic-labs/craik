"""Audited vendor-CLI execution (Task 5.5b).

The CLI counterpart of the cores in ``backend.adapters.audited_core``: it owns
the audited run/receipt persistence for ``gemini`` / ``codex`` subprocess runs
and the typed-emission composer the live CLI ``run()`` bodies share. It lives in
its own package because both ``backend`` and ``backend/adapters`` are at the
sibling-module layout cap; the subprocess pump itself lives in
``sandbox.cli_stream``.
"""

from __future__ import annotations
