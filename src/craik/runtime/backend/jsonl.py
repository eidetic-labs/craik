"""JSONL stdio transport for the local Craik Gateway session."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, TextIO

from craik.runtime.backend.event_contract import (
    format_gateway_event_contract_issues,
    validate_gateway_event,
)
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.session import execute_prompt
from craik.runtime.model_commands import model_set_result, parse_model_options
from craik.runtime.reviewing.approval_commands import approvals_decide_result
from craik.runtime.shell.contract_runtime.builtin_slash_commands import (
    CLAUDE_PERMISSION_MODE_ENV,
)
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_specs
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.shell.slash_command_schema import SlashCommandSpec
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_widgets.theme_settings import current_theme
from craik.runtime.store import LocalStore


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
        issues = validate_gateway_event(payload)
        if issues:
            raise ValueError(
                "Gateway backend emitted invalid event: "
                f"{format_gateway_event_contract_issues(issues)}"
            )
        output_stream.write(json.dumps(payload, sort_keys=True) + "\n")
        output_stream.flush()

    emit(
        BackendEvent(
            type="session.ready",
            data={
                "transport": "jsonl.stdio",
                "protocol": "craik.tui.gateway",
                "protocol_version": "1",
                "client": "craik-tui",
                "capabilities": [
                    "prompt.submit",
                    "slash.submit",
                    "slash.catalog",
                    "approval.decide",
                    "model.set",
                    "run.interrupt",
                    "session.status",
                    "session.history",
                ],
            },
        )
    )
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
            if message_type == "session.history":
                emit(
                    BackendEvent(
                        type="session.history",
                        data={"receipts": _recent_receipts(env)},
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
                                _slash_catalog_entry(spec, env)
                                for spec in get_tui_slash_specs()
                            ],
                        },
                    )
                )
                continue
            if message_type in {"session.close", "exit", "quit"}:
                break
            raise ValueError(
                f"unsupported JSONL message type: {message_type!r}; "
                "supported types are session.status, prompt.submit, slash.submit, "
                "slash.catalog, approval.decide, model.set, run.interrupt, "
                "session.history, session.close"
            )
        except Exception as error:
            emit(BackendEvent(type="error", data={"message": str(error)}))
    return 0


def _slash_catalog_entry(
    spec: SlashCommandSpec,
    env: dict[str, str] | None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": spec.command_name,
        "usage": spec.usage,
        "summary": spec.summary,
        "aliases": list(spec.aliases),
        "requires_confirmation": spec.requires_confirmation,
    }
    if spec.choices:
        entry["choices"] = {key: list(values) for key, values in spec.choices.items()}
    subcommands = _usage_subcommands(spec.usage)
    if subcommands:
        entry["subcommands"] = subcommands
    current_value = _current_catalog_value(spec.command_name, env)
    if current_value is not None:
        entry["current_value"] = current_value
    return entry


def _usage_subcommands(usage: str) -> list[str]:
    if "[" not in usage or "]" not in usage:
        return []
    inner = usage.split("[", 1)[1].split("]", 1)[0]
    return [
        token
        for token in inner.replace("|", " ").split()
        if not token.startswith("<")
        and all(character.isalpha() or character == "-" for character in token)
    ]


def _current_catalog_value(command_name: str, env: dict[str, str] | None) -> str | None:
    if command_name == "mode":
        values = os.environ if env is None else env
        return values.get(CLAUDE_PERMISSION_MODE_ENV, "default")
    if command_name == "theme":
        return current_theme(env)
    return None


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


def _recent_receipts(env: dict[str, str] | None) -> list[dict[str, object]]:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        receipts = sorted(
            store.list_receipts(),
            key=lambda receipt: (receipt.created_at, receipt.id),
            reverse=True,
        )
        return [
            {
                "id": receipt.id,
                "task_id": receipt.task_id,
                "actor": receipt.actor,
                "capability": receipt.capability,
                "target": receipt.target,
                "policy": receipt.policy_profile,
                "reason": receipt.reason,
                "status": receipt.result.status,
                "summary": receipt.result.summary,
                "created_at": receipt.created_at.isoformat(),
                "auth_profile_id": receipt.auth_profile_id,
                "operator_subject": receipt.operator_subject,
                "tools": _metadata_strings(receipt.result.metadata, "tools"),
                "files": _metadata_strings(receipt.result.metadata, "files"),
                "commands": _metadata_strings(receipt.result.metadata, "commands"),
                "approvals": _metadata_strings(receipt.result.metadata, "approvals"),
                "outputs": _metadata_strings(receipt.result.metadata, "outputs"),
                "evidence_ids": _metadata_strings(receipt.result.metadata, "evidence_ids"),
                "handoff_ids": _metadata_strings(receipt.result.metadata, "handoff_ids"),
            }
            for receipt in receipts[:12]
        ]
    finally:
        store.close()


def _metadata_strings(metadata: dict[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]
