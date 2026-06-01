"""Shared socket wire-framing for the hook bridge (STDLIB-ONLY).

Both halves of the hook bridge frame messages identically: newline-delimited
UTF-8 JSON, one message per direction. The framing previously lived in two
near-verbatim copies -- the thin ``craik-hook`` client
(:mod:`craik.runtime.hooks.client`) and the gateway-side server
(:mod:`craik.runtime.backend.adapters.hook_bridge`). Two copies of a wire
protocol can silently drift (client framing vs server framing desync is a real
bug class), so the single source of truth lives here.

This module imports ONLY stdlib (``json`` / ``socket`` / ``typing``) so the
thin client importing it does NOT pull in ``backend.events`` /
``backend.adapters``. Keeping that import chain tiny is the whole point of the
``craik-hook`` thin-entry split.

The framing behavior is the EXACT pre-split implementation: do not change it
without changing both sides in lockstep (that is precisely the desync this
module exists to prevent).
"""

from __future__ import annotations

import json
import socket
from typing import Any

# Transport framing: newline-delimited UTF-8 JSON, one message per direction.
_RECV_CHUNK = 65536


def _read_message(conn: socket.socket) -> dict[str, Any] | None:
    buffer = bytearray()
    while b"\n" not in buffer:
        chunk = conn.recv(_RECV_CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
    raw = bytes(buffer).split(b"\n", 1)[0].decode("utf-8", errors="replace")
    return _decode_payload(raw)


def _decode_payload(raw: str) -> dict[str, Any] | None:
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _write_message(conn: socket.socket, payload: dict[str, Any]) -> None:
    conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


__all__ = [
    "_RECV_CHUNK",
    "_decode_payload",
    "_read_message",
    "_write_message",
]
