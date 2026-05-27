"""JSONL stdio transport for the local Craik Gateway session."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.session import execute_prompt
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command


def run_jsonl_gateway(
    *,
    env: dict[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run a local JSONL request/response loop for Gateway clients."""
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout

    def emit(event: BackendEvent | dict[str, Any]) -> None:
        payload = event.as_dict() if isinstance(event, BackendEvent) else event
        output_stream.write(json.dumps(payload, sort_keys=True) + "\n")
        output_stream.flush()

    emit(BackendEvent(type="session.ready", data={"transport": "jsonl.stdio"}))
    for line in input_stream:
        raw = line.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError("JSONL message must be an object")
            message_type = message.get("type")
            if message_type == "session.status":
                emit(
                    BackendEvent(
                        type="session.status",
                        data=resolve_readiness(env).as_dict(),
                    )
                )
                continue
            if message_type == "prompt.submit":
                text = _required_text(message)
                execute_prompt(
                    text,
                    env=env,
                    source="jsonl",
                    stream=emit,
                )
                continue
            if message_type == "slash.submit":
                text = _required_text(message)
                result = dispatch_slash_command(text, env=env)
                emit(
                    BackendEvent(
                        type="slash.completed",
                        data={
                            "text": result.text,
                            "exit_code": result.exit_code,
                            "payload": result.payload,
                            "shape": result.payload_shape,
                        },
                    )
                )
                continue
            if message_type in {"session.close", "exit", "quit"}:
                break
            raise ValueError(f"unsupported JSONL message type: {message_type!r}")
        except Exception as error:
            emit(BackendEvent(type="error", data={"message": str(error)}))
    return 0


def _required_text(message: dict[str, Any]) -> str:
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{message.get('type')} requires non-empty text")
    return text
