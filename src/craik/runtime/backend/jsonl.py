"""JSONL stdio transport for the local Craik Gateway session."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.session import execute_prompt
from craik.runtime.model_commands import model_set_result, parse_model_options
from craik.runtime.reviewing.approval_commands import approvals_decide_result
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_specs
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
            if message_type == "model.set":
                model = _required_model(message)
                options = _model_options(message)
                result = model_set_result(
                    model,
                    env=env,
                    display_name=_string_or_none(message.get("display_name")),
                    backend=_string_or_default(message.get("backend"), "provider"),
                    options=options,
                )
                emit(
                    BackendEvent(
                        type="model.changed",
                        data={
                            "model": model,
                            "payload": result.payload,
                        },
                    )
                )
                continue
            if message_type == "approval.decide":
                approval_id = _required_string(message, "approval_id")
                decision = _required_string(message, "decision")
                reason = _required_string(message, "reason")
                operator = _string_or_default(message.get("operator"), "user:jsonl")
                result = approvals_decide_result(
                    approval_id,
                    decision=decision,
                    operator=operator,
                    reason=reason,
                    env=env,
                )
                emit(
                    BackendEvent(
                        type="approval.resolved",
                        data={
                            "approval_id": approval_id,
                            "decision": decision,
                            "payload": result.payload,
                        },
                    )
                )
                continue
            if message_type == "run.interrupt":
                run_id = _required_string(message, "run_id")
                emit(
                    BackendEvent(
                        type="run.interrupt.requested",
                        run_id=run_id,
                        data={
                            "run_id": run_id,
                            "reason": _string_or_default(
                                message.get("reason"),
                                "interrupt requested by Gateway client",
                            ),
                        },
                    )
                )
                continue
            if message_type == "slash.submit":
                text = _required_text(message)
                slash_result = dispatch_slash_command(text, env=env)
                emit(
                    BackendEvent(
                        type="slash.completed",
                        data={
                            "text": slash_result.text,
                            "exit_code": slash_result.exit_code,
                            "payload": slash_result.payload,
                            "shape": slash_result.payload_shape,
                        },
                    )
                )
                continue
            if message_type == "slash.catalog":
                emit(
                    BackendEvent(
                        type="slash.catalog",
                        data={
                            "commands": [
                                {
                                    "name": spec.command_name,
                                    "usage": spec.usage,
                                    "summary": spec.summary,
                                    "aliases": list(spec.aliases),
                                }
                                for spec in get_tui_slash_specs()
                            ],
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


def _required_model(message: dict[str, Any]) -> str:
    return _required_string(message, "model")


def _required_string(message: dict[str, Any], field: str) -> str:
    value = message.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{message.get('type')} requires non-empty {field}")
    return value


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value.strip() else default


def _model_options(message: dict[str, Any]) -> dict[str, object]:
    passthrough = message.get("options")
    option_items = [
        f"{key}={value}"
        for key, value in passthrough.items()
        if isinstance(key, str)
    ] if isinstance(passthrough, dict) else []
    return parse_model_options(
        reasoning_effort=_string_or_none(message.get("reasoning_effort")),
        service_tier=_string_or_none(message.get("service_tier")),
        temperature=_float_or_none(message.get("temperature")),
        max_output_tokens=_int_or_none(message.get("max_output_tokens")),
        passthrough=option_items,
    )


def _float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None
