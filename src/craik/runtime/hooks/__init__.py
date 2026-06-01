"""Thin, dependency-light home for the ``craik-hook`` CLI gating client.

This package exists so the ``craik-hook`` console script
(:func:`craik.runtime.hooks.client.craik_hook_main`) can be imported WITHOUT
dragging in the backend adapter stack (``backend.events`` / the six concrete
adapters / ``google.auth`` / etc.). The hook fires on every CLI tool call once
live, so its per-invocation import cost must stay minimal. Importing this
package triggers only ``craik`` + ``craik.runtime`` (light meta-path/alias
setup) plus :mod:`craik.runtime.hooks.client`, which imports only stdlib.

The gateway-side server (``HookBridgeServer``) deliberately stays in
:mod:`craik.runtime.backend.adapters.hook_bridge`; its import cost does not
matter because the gateway already loads the heavy stack.
"""

from __future__ import annotations
