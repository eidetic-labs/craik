"""Session export/import compatibility helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from craik.contracts.models import AgentSessionEvent, AgentSessionState, CraikModel
from craik.runtime.policy.redaction import redact

SessionImportSourceKind = Literal["craik", "adjacent-transcript"]


class SessionUnsupportedField(CraikModel):
    """Unsupported source field preserved as non-executable migration evidence."""

    path: str
    reason: str
    value_summary: str | None = None


class SessionPortabilityProvenance(CraikModel):
    """Original source identity for an exported or imported session."""

    source_kind: SessionImportSourceKind
    source_session_id: str
    source_name: str | None = None
    source_path: str | None = None
    imported: bool = False


class CraikSessionExport(CraikModel):
    """Portable, redacted Craik session export."""

    schema_: Literal["craik.session_export"] = Field(
        default="craik.session_export",
        alias="schema",
    )
    version: Literal["0.12.0"] = "0.12.0"
    exported_at: datetime
    session: AgentSessionState
    events: list[AgentSessionEvent] = Field(default_factory=list)
    provenance: SessionPortabilityProvenance
    unsupported_fields: list[SessionUnsupportedField] = Field(default_factory=list)
    redacted: bool = True


def export_agent_session(
    session: AgentSessionState,
    events: list[AgentSessionEvent],
    *,
    now: datetime | None = None,
) -> CraikSessionExport:
    """Export a Craik session with redacted event metadata."""
    exported_at = now or datetime.now(UTC)
    safe_session = session.model_copy(
        update={
            "pid": None,
            "endpoint_url": None,
            "redacted": True,
            "recovery_metadata": _redacted_mapping(session.recovery_metadata),
        }
    )
    safe_events = [
        event.model_copy(
            update={
                "metadata": _redacted_mapping(event.metadata),
                "recovery_metadata": _redacted_mapping(event.recovery_metadata),
                "redacted": True,
                "receipt_hmac": None,
            }
        )
        for event in events
        if event.session_id == session.id
    ]
    return CraikSessionExport(
        exported_at=exported_at,
        session=safe_session,
        events=safe_events,
        provenance=SessionPortabilityProvenance(
            source_kind="craik",
            source_session_id=session.id,
        ),
        redacted=True,
    )


def import_session_export(path: Path, *, now: datetime | None = None) -> CraikSessionExport:
    """Import a Craik session export or adjacent transcript JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("session import requires a JSON object")
    if payload.get("schema") == "craik.session_export":
        return _import_craik_export(payload, source_path=path, now=now)
    return _import_adjacent_transcript(payload, source_path=path, now=now)


def session_export_payload(export: CraikSessionExport) -> dict[str, Any]:
    """Return a JSON-ready portable session payload."""
    return export.model_dump(mode="json", by_alias=True)


def _import_craik_export(
    payload: dict[str, Any],
    *,
    source_path: Path,
    now: datetime | None,
) -> CraikSessionExport:
    imported = CraikSessionExport.model_validate(payload)
    timestamp = now or datetime.now(UTC)
    metadata = {
        **imported.session.recovery_metadata,
        "imported": True,
        "import_source_kind": "craik",
        "source_session_id": imported.provenance.source_session_id,
        "source_path": str(source_path),
    }
    session = imported.session.model_copy(
        update={
            "id": f"imported_{imported.session.id}",
            "status": "stopped",
            "pid": None,
            "endpoint_url": None,
            "stopped_at": timestamp,
            "updated_at": timestamp,
            "recovery_metadata": metadata,
            "redacted": True,
            "receipt_hmac": None,
        }
    )
    events = [
        event.model_copy(
            update={
                "id": f"imported_{event.id}",
                "session_id": session.id,
                "metadata": _redacted_mapping(event.metadata),
                "recovery_metadata": _redacted_mapping(event.recovery_metadata),
                "redacted": True,
                "receipt_hmac": None,
            }
        )
        for event in imported.events
    ]
    return imported.model_copy(
        update={
            "exported_at": timestamp,
            "session": session,
            "events": events,
            "provenance": imported.provenance.model_copy(
                update={"source_path": str(source_path), "imported": True}
            ),
            "redacted": True,
        }
    )


def _import_adjacent_transcript(
    payload: dict[str, Any],
    *,
    source_path: Path,
    now: datetime | None,
) -> CraikSessionExport:
    timestamp = now or datetime.now(UTC)
    source_session_id = str(
        payload.get("session_id")
        or payload.get("id")
        or payload.get("conversation_id")
        or source_path.stem
    )
    source_name = _string_or_none(payload.get("name") or payload.get("title"))
    messages = _message_list(payload)
    unsupported = _unsupported_fields(payload, messages)
    session_id = f"imported_{_slug(source_session_id)}"
    session = AgentSessionState(
        id=session_id,
        project_id=_string_or_none(payload.get("project_id")),
        operator_subject="imported-session",
        provider_id=_string_or_none(payload.get("provider")) or "imported-provider",
        model_id=_string_or_none(payload.get("model")),
        mode="foreground",
        status="stopped",
        started_at=timestamp,
        last_activity_at=timestamp,
        stopped_at=timestamp,
        updated_at=timestamp,
        recovery_metadata={
            "imported": True,
            "import_source_kind": "adjacent-transcript",
            "source_session_id": source_session_id,
            "source_name": source_name,
            "source_path": str(source_path),
            "unsupported_field_count": len(unsupported),
        },
        supervision_notes=[
            "Imported from adjacent transcript; unsupported tool calls remain non-executable."
        ],
        redacted=True,
    )
    events = [
        _event_from_message(
            message,
            index=index,
            session=session,
            now=timestamp,
        )
        for index, message in enumerate(messages)
    ]
    return CraikSessionExport(
        exported_at=timestamp,
        session=session,
        events=events,
        provenance=SessionPortabilityProvenance(
            source_kind="adjacent-transcript",
            source_session_id=source_session_id,
            source_name=source_name,
            source_path=str(source_path),
            imported=True,
        ),
        unsupported_fields=unsupported,
        redacted=True,
    )


def _message_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages = payload.get("messages", payload.get("transcript", []))
    if not isinstance(messages, list):
        raise ValueError("session transcript messages must be a list")
    return [message for message in messages if isinstance(message, dict)]


def _unsupported_fields(
    payload: dict[str, Any],
    messages: list[dict[str, Any]],
) -> list[SessionUnsupportedField]:
    unsupported: list[SessionUnsupportedField] = []
    for field in ("system_prompt", "tools", "tool_results", "attachments"):
        if field in payload:
            unsupported.append(
                SessionUnsupportedField(
                    path=f"$.{field}",
                    reason="source field is preserved as evidence only, not executable authority",
                    value_summary=_summary(payload[field]),
                )
            )
    for index, message in enumerate(messages):
        for field in ("tool_calls", "function_call", "tool_results"):
            if field in message:
                unsupported.append(
                    SessionUnsupportedField(
                        path=f"$.messages[{index}].{field}",
                        reason="unsupported tool calls do not become executable authority",
                        value_summary=_summary(message[field]),
                    )
                )
    return unsupported


def _event_from_message(
    message: dict[str, Any],
    *,
    index: int,
    session: AgentSessionState,
    now: datetime,
) -> AgentSessionEvent:
    role = str(message.get("role") or message.get("speaker") or "message")
    content = message.get("content", message.get("text", ""))
    metadata = _redacted_mapping(
        {
            "role": role,
            "content": content,
            "source_index": index,
            "imported": True,
            "unsupported_tool_call_count": _tool_call_count(message),
        }
    )
    return AgentSessionEvent(
        id=f"{session.id}_event_{index + 1}",
        session_id=session.id,
        event_type=f"imported.{role}",
        operator_subject=session.operator_subject,
        project_id=session.project_id,
        provider_id=session.provider_id,
        model_id=session.model_id,
        policy_envelope_id=session.policy_envelope_id,
        metadata=metadata,
        created_at=now,
        redacted=True,
    )


def _redacted_mapping(value: dict[str, Any]) -> dict[str, Any]:
    redacted = redact(value).value
    return redacted if isinstance(redacted, dict) else {}


def _tool_call_count(message: dict[str, Any]) -> int:
    count = 0
    for field in ("tool_calls", "tool_results"):
        value = message.get(field)
        if isinstance(value, list):
            count += len(value)
        elif value is not None:
            count += 1
    if message.get("function_call") is not None:
        count += 1
    return count


def _summary(value: Any) -> str:
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, dict):
        return f"object[{len(value)}]"
    return type(value).__name__


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in value)
    return slug.strip("_") or "session"
