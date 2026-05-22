"""Shared support helpers for read-only operator CLI commands."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, cast

import typer

from craik.contracts.models import ContradictionStatus
from craik.runtime.companions.operator_views import OperatorSurfaceSnapshot
from craik.runtime.policy.redaction import redact
from craik.runtime.policy.text import sanitize_runtime_text
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore


def project_scope(store: LocalStore, project_id_or_name: str | None) -> str | None:
    projects = store.list_projects()
    if project_id_or_name:
        resolved = ProjectRegistry(store).get_project(project_id_or_name)
        if resolved is None:
            raise typer.BadParameter(f"unknown project: {project_id_or_name}") from None
        return resolved.id
    if len(projects) == 1:
        return projects[0].id
    if len(projects) > 1:
        raise typer.BadParameter("--project required when multiple projects are registered")
    return None


def require_section(
    snapshot: OperatorSurfaceSnapshot,
    section_id: str,
) -> OperatorSurfaceSnapshot:
    sections = [section for section in snapshot.sections if section.id == section_id]
    if not sections:
        known = ", ".join(section.id for section in snapshot.sections)
        raise typer.BadParameter(f"unknown operator section {section_id!r}; known: {known}")
    return OperatorSurfaceSnapshot(
        project_id=snapshot.project_id,
        read_only=snapshot.read_only,
        sections=sections,
        notes=snapshot.notes,
    )


def contradiction_status(value: str) -> ContradictionStatus:
    if value not in {"open", "resolved", "ignored"}:
        raise typer.BadParameter(f"unsupported contradiction status: {value}")
    return cast(ContradictionStatus, value)


def task_ids_for_project(store: LocalStore, project_id: str | None) -> set[str] | None:
    if project_id is None:
        return None
    return {task.id for task in store.list_tasks() if task.project_id == project_id}


def record_in_project(
    record: Any,
    project_id: str | None,
    task_ids: set[str] | None = None,
) -> bool:
    if project_id is None:
        return True
    record_project_id = getattr(record, "project_id", None)
    if record_project_id is not None:
        return bool(record_project_id == project_id)
    metadata = getattr(record, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("project_id") is not None:
        return bool(metadata.get("project_id") == project_id)
    record_task_id = getattr(record, "task_id", None)
    if record_task_id is not None and task_ids is not None:
        return record_task_id in task_ids
    if isinstance(metadata, dict) and metadata.get("task_id") is not None:
        return task_ids is not None and metadata.get("task_id") in task_ids
    return False


def receipt_hmac_status(receipt: Any | None) -> str:
    if receipt is None:
        return "unknown"
    receipt_hmac = getattr(receipt, "receipt_hmac", None)
    return "verified" if receipt_hmac else "unverified"


def receipt_json(receipt: Any, hmac_status: str) -> Any:
    payload = json_ready(receipt)
    if isinstance(payload, dict):
        payload["hmac_verification"] = hmac_status
    return payload


def json_ready(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return sanitize_runtime_text(str(redact(value).value))
    if is_dataclass(value):
        return {
            field.name: json_ready(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value
