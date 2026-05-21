"""Instruction source snapshot refresh helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import (
    InstructionSource,
    InstructionSourceHashStatus,
    InstructionSourceSnapshot,
)
from craik.runtime.projects.instruction_ingestion import (
    InstructionIngestionError,
    parse_instruction_source,
)
from craik.runtime.store import LocalStore


class InstructionSourceSnapshotError(RuntimeError):
    """Raised when instruction source snapshots cannot be refreshed."""


MAX_INSTRUCTION_SOURCE_BYTES = 10 * 1024 * 1024
MAX_PROJECT_INSTRUCTION_SOURCE_BYTES = 100 * 1024 * 1024


def compute_source_snapshot(
    source: InstructionSource,
    *,
    base_dir: Path,
    previous_snapshot: InstructionSourceSnapshot | None = None,
    now: datetime | None = None,
) -> InstructionSourceSnapshot:
    """Compute the current SHA-256 snapshot for one registered source file.

    Source paths are read through the #606 parser, so the same project-root
    confinement and source-kind validation apply before bytes are hashed.
    """
    captured_at = now or datetime.now(UTC)
    oversize = _oversize_source_snapshot(source, base_dir=base_dir, now=captured_at)
    if oversize is not None:
        return oversize
    try:
        parsed = parse_instruction_source(source, base_dir=base_dir)
    except InstructionIngestionError as exc:
        if _is_missing_source_error(exc):
            return InstructionSourceSnapshot(
                id=f"instruction_snapshot_{source.id}_missing",
                project_id=source.project_id,
                source_id=source.id,
                path=source.path,
                content_hash=None,
                hash_status="missing",
                byte_count=None,
                line_count=None,
                captured_at=captured_at,
            )
        raise

    normalized_bytes = _normalize_newlines(parsed.raw_bytes)
    content_hash = hashlib.sha256(normalized_bytes).hexdigest()
    status: InstructionSourceHashStatus = (
        "new"
        if previous_snapshot is None
        else "unchanged"
        if previous_snapshot.content_hash == content_hash
        else "changed"
    )
    return InstructionSourceSnapshot(
        id=f"instruction_snapshot_{source.id}_{content_hash[:12]}",
        project_id=source.project_id,
        source_id=source.id,
        path=source.path,
        content_hash=content_hash,
        hash_status=status,
        byte_count=len(normalized_bytes),
        line_count=_line_count(normalized_bytes),
        captured_at=captured_at,
    )


def refresh_project_snapshots(
    store: LocalStore,
    project_id: str,
    *,
    now: datetime | None = None,
) -> list[InstructionSourceSnapshot]:
    """Refresh and persist snapshots for every active source in a project."""
    project = store.get_project(project_id)
    if project is None:
        raise InstructionSourceSnapshotError(f"unknown project: {project_id}")

    base_dir = Path(project.repo.local_path).expanduser().resolve()
    previous_by_source = _latest_snapshots_by_source(
        snapshot
        for snapshot in store.list_instruction_source_snapshots()
        if snapshot.project_id == project_id
    )
    snapshots: list[InstructionSourceSnapshot] = []
    project_byte_count = 0
    for source in _active_project_sources(store, project_id):
        source_size = _source_size(source, base_dir=base_dir)
        if source_size is not None:
            project_byte_count += source_size
            if project_byte_count > MAX_PROJECT_INSTRUCTION_SOURCE_BYTES:
                snapshots.append(
                    _oversize_snapshot(
                        source,
                        size=source_size,
                        now=now or datetime.now(UTC),
                    )
                )
                continue
        snapshots.append(
            compute_source_snapshot(
                source,
                base_dir=base_dir,
                previous_snapshot=previous_by_source.get(source.id),
                now=now,
            )
        )
    for snapshot in snapshots:
        store.put_instruction_source_snapshot(snapshot)
    return sorted(snapshots, key=lambda snapshot: (snapshot.path, snapshot.source_id))


def _active_project_sources(store: LocalStore, project_id: str) -> list[InstructionSource]:
    registry = store.get_instruction_source_registry(f"instruction_source_registry_{project_id}")
    if registry is not None:
        active_ids = set(registry.active_source_ids)
        sources = [source for source in registry.sources if source.id in active_ids]
    else:
        sources = [
            source
            for source in store.list_instruction_sources()
            if source.project_id == project_id and source.active
        ]
    return sorted(sources, key=lambda source: (source.path, source.id))


def _latest_snapshots_by_source(
    snapshots: Iterable[InstructionSourceSnapshot],
) -> dict[str, InstructionSourceSnapshot]:
    latest: dict[str, InstructionSourceSnapshot] = {}
    for snapshot in snapshots:
        existing = latest.get(snapshot.source_id)
        if existing is None or (snapshot.captured_at, snapshot.id) > (
            existing.captured_at,
            existing.id,
        ):
            latest[snapshot.source_id] = snapshot
    return latest


def _normalize_newlines(raw_bytes: bytes) -> bytes:
    return raw_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _oversize_source_snapshot(
    source: InstructionSource,
    *,
    base_dir: Path,
    now: datetime,
) -> InstructionSourceSnapshot | None:
    size = _source_size(source, base_dir=base_dir)
    if size is None or size <= MAX_INSTRUCTION_SOURCE_BYTES:
        return None
    return _oversize_snapshot(source, size=size, now=now)


def _source_size(source: InstructionSource, *, base_dir: Path) -> int | None:
    root = base_dir.resolve()
    abs_path = (root / source.path).resolve()
    try:
        abs_path.relative_to(root)
    except ValueError:
        return None
    try:
        return abs_path.stat().st_size
    except OSError:
        return None


def _oversize_snapshot(
    source: InstructionSource,
    *,
    size: int,
    now: datetime,
) -> InstructionSourceSnapshot:
    return InstructionSourceSnapshot(
        id=f"instruction_snapshot_{source.id}_oversize",
        project_id=source.project_id,
        source_id=source.id,
        path=source.path,
        content_hash=None,
        hash_status="oversize",
        byte_count=size,
        line_count=None,
        captured_at=now,
    )


def _line_count(raw_bytes: bytes) -> int:
    if not raw_bytes:
        return 0
    return len(raw_bytes.decode("utf-8").splitlines())


def _is_missing_source_error(exc: InstructionIngestionError) -> bool:
    message = str(exc)
    return "does not exist" in message or "not a file" in message
