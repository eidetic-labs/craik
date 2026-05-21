import hashlib
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from craik.contracts.models import (
    INSTRUCTION_SOURCE_DEFAULT_PATHS,
    InstructionProvenance,
    InstructionSource,
    InstructionSourceSnapshot,
)
from craik.runtime.instruction_provenance import (
    extract_instruction_provenance,
    persist_instruction_provenance,
)
from craik.runtime.instruction_snapshots import compute_source_snapshot
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.instruction_ingestion import parse_instruction_source
from craik.runtime.projects.instruction_sources import (
    render_instruction_provenance_markdown,
    render_instruction_snapshot_json,
)
from craik.runtime.store import LocalStore

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "instructions"
FIXTURE_FILES: dict[str, str] = {
    "agents_md": "agents.md",
    "claude_md": "claude.md",
    "gemini_md": "gemini.md",
    "hermes_md": "hermes.md",
    "skills_md": "skills.md",
    "cursor_rules": "cursorrules",
    "github_copilot_instructions": "copilot-instructions.md",
    "codex_instructions": "codex-instructions.md",
    "policy_doc": "policy.md",
}


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _snapshot(status: str, content_hash: str | None = "abc123") -> InstructionSourceSnapshot:
    return InstructionSourceSnapshot(
        id=f"instruction_snapshot_{status}",
        project_id="project_docs",
        source_id="instruction_source_agents_md",
        path="AGENTS.md",
        content_hash=content_hash,
        hash_status=status,
        byte_count=128 if content_hash else None,
        line_count=12 if content_hash else None,
        captured_at="2026-05-15T22:30:00Z",
    )


def _source(kind: str, path: str) -> InstructionSource:
    return InstructionSource(
        id=f"instruction_source_{kind}",
        project_id="project_docs",
        kind=kind,
        path=path,
        owner="team:runtime",
        declared_by="agent:orchestrator",
        created_at="2026-05-20T00:00:00Z",
    )


def _stage_source(tmp_path: Path, kind: str) -> InstructionSource:
    declared = INSTRUCTION_SOURCE_DEFAULT_PATHS[kind]
    if kind == "policy_doc":
        declared = "docs/runtime-policy.md"
    destination = tmp_path / declared
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / FIXTURE_FILES[kind], destination)
    return _source(kind, declared)


@pytest.mark.parametrize("status", ["unchanged", "changed", "new"])
def test_present_instruction_source_hash_states(status: str) -> None:
    snapshot = _snapshot(status)

    assert snapshot.hash_status == status
    assert snapshot.content_hash == "abc123"


def test_missing_instruction_source_hash_state_omits_hash() -> None:
    snapshot = _snapshot("missing", content_hash=None)

    assert snapshot.hash_status == "missing"
    assert snapshot.content_hash is None


def test_snapshot_and_provenance_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        snapshot = _snapshot("unchanged")
        provenance = InstructionProvenance(
            id="instruction_provenance_agents_rule",
            project_id="project_docs",
            source_id=snapshot.source_id,
            snapshot_id=snapshot.id,
            path=snapshot.path,
            start_line=3,
            end_line=5,
            start_column=1,
            end_column=80,
            summary="Instruction rule with line-range provenance.",
            excerpt_hash="def456",
            captured_at="2026-05-15T22:31:00Z",
        )

        store.put_instruction_source_snapshot(snapshot)
        store.put_instruction_provenance(provenance)

        assert store.get_instruction_source_snapshot(snapshot.id) == snapshot
        assert store.get_instruction_provenance(provenance.id) == provenance
        assert store.list_instruction_source_snapshots() == [snapshot]
        assert store.list_instruction_provenance() == [provenance]
        assert render_instruction_snapshot_json(snapshot) == render_instruction_snapshot_json(
            InstructionSourceSnapshot.model_validate_json(render_instruction_snapshot_json(snapshot))
        )
        assert "AGENTS.md:3-5" in render_instruction_provenance_markdown(provenance)
    finally:
        store.close()


@pytest.mark.parametrize("kind", list(FIXTURE_FILES))
def test_extracts_and_persists_provenance_for_each_source_kind(
    tmp_path: Path,
    kind: str,
) -> None:
    store = _store(tmp_path)
    try:
        source = _stage_source(tmp_path, kind)
        parsed = parse_instruction_source(source, base_dir=tmp_path)
        snapshot = compute_source_snapshot(source, base_dir=tmp_path)
        store.put_instruction_source_snapshot(snapshot)

        records = persist_instruction_provenance(
            store,
            parsed,
            snapshot=snapshot,
            project_id=source.project_id,
        )

        assert len(records) == len(parsed.statements)
        assert {record.id for record in store.list_instruction_provenance()} == {
            record.id for record in records
        }
        source_lines = (tmp_path / source.path).read_text(encoding="utf-8").splitlines()
        for statement, record in zip(parsed.statements, records, strict=True):
            assert record.project_id == source.project_id
            assert record.source_id == snapshot.source_id
            assert record.snapshot_id == snapshot.id
            assert record.path == source.path
            assert record.start_line == statement.start_line
            assert record.end_line == statement.end_line
            assert record.start_column == statement.start_column
            assert record.end_column == statement.end_column
            assert 1 <= record.start_line <= len(source_lines)
            assert record.end_line <= len(source_lines)
            assert record.summary == statement.text.splitlines()[0].strip()[:200]
            assert record.excerpt_hash == hashlib.sha256(
                statement.text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
            ).hexdigest()
    finally:
        store.close()


def test_excerpt_hash_normalizes_newlines(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "lf-policy.md").write_text("Line one.\nLine two.\n", encoding="utf-8")
    (tmp_path / "docs" / "crlf-policy.md").write_bytes(b"Line one.\r\nLine two.\r\n")
    source = _source("policy_doc", "docs/lf-policy.md")
    snapshot = _snapshot("new").model_copy(update={"path": "docs/lf-policy.md"})
    lf = parse_instruction_source(
        source,
        base_dir=tmp_path,
    )
    crlf = parse_instruction_source(
        source.model_copy(update={"path": "docs/crlf-policy.md"}),
        base_dir=tmp_path,
    )

    lf_record = extract_instruction_provenance(
        lf,
        snapshot=snapshot,
        project_id=source.project_id,
    )[0]
    crlf_record = extract_instruction_provenance(
        crlf,
        snapshot=snapshot.model_copy(update={"path": "docs/crlf-policy.md"}),
        project_id=source.project_id,
    )[0]

    assert lf_record.excerpt_hash == crlf_record.excerpt_hash


def test_provenance_extraction_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        source = _stage_source(tmp_path, "agents_md")
        parsed = parse_instruction_source(source, base_dir=tmp_path)
        snapshot = compute_source_snapshot(source, base_dir=tmp_path)

        first = extract_instruction_provenance(
            parsed,
            snapshot=snapshot,
            project_id=source.project_id,
        )
        second = extract_instruction_provenance(
            parsed,
            snapshot=snapshot,
            project_id=source.project_id,
        )
        assert [item.model_dump(mode="json", by_alias=True) for item in first] == [
            item.model_dump(mode="json", by_alias=True) for item in second
        ]

        persist_instruction_provenance(
            store,
            parsed,
            snapshot=snapshot,
            project_id=source.project_id,
        )
        persist_instruction_provenance(
            store,
            parsed,
            snapshot=snapshot,
            project_id=source.project_id,
        )
        assert [record.id for record in store.list_instruction_provenance()] == [
            record.id for record in first
        ]
    finally:
        store.close()


def test_source_level_provenance_fallback_has_no_range() -> None:
    provenance = InstructionProvenance(
        id="instruction_provenance_source_level",
        project_id="project_docs",
        source_id="instruction_source_agents_md",
        path="AGENTS.md",
        summary="Source-level fallback when line ranges are unavailable.",
        captured_at="2026-05-15T22:31:00Z",
    )

    assert "- Location: AGENTS.md\n" in render_instruction_provenance_markdown(provenance)


def test_missing_sources_reject_hashes() -> None:
    with pytest.raises(ValidationError, match="must not include content_hash"):
        _snapshot("missing", content_hash="abc123")


def test_present_sources_require_hashes() -> None:
    with pytest.raises(ValidationError, match="require content_hash"):
        _snapshot("changed", content_hash=None)


def test_line_ranges_require_start_and_end() -> None:
    with pytest.raises(ValidationError, match="start_line and end_line"):
        InstructionProvenance(
            id="instruction_provenance_invalid",
            project_id="project_docs",
            source_id="instruction_source_agents_md",
            path="AGENTS.md",
            start_line=3,
            summary="Invalid partial range.",
            captured_at="2026-05-15T22:31:00Z",
        )
