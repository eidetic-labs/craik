"""Tests for instruction-source parsers (issue #606)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from craik.contracts.models import (
    INSTRUCTION_SOURCE_DEFAULT_PATHS,
    InstructionSource,
)
from craik.runtime.projects.instruction_ingestion import (
    InstructionIngestionError,
    parse_instruction_source,
)

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

EXPECTED_STATEMENT_COUNT: dict[str, int] = {
    "agents_md": 4,
    "claude_md": 2,
    "gemini_md": 1,
    "hermes_md": 2,
    "skills_md": 2,
    "cursor_rules": 3,
    "github_copilot_instructions": 2,
    "codex_instructions": 2,
    "policy_doc": 2,
}


def _make_source(kind: str, path: str) -> InstructionSource:
    return InstructionSource(
        id=f"instruction_source_{kind}",
        project_id="project_test",
        kind=kind,
        path=path,
        owner="team:runtime",
        declared_by="agent:orchestrator",
        created_at="2026-05-20T00:00:00Z",
    )


def _stage(tmp_path: Path, kind: str, *, path: str | None = None) -> InstructionSource:
    """Copy the fixture file into tmp_path at the declared path for the kind."""
    declared = path or INSTRUCTION_SOURCE_DEFAULT_PATHS[kind] or FIXTURE_FILES[kind]
    dest = tmp_path / declared
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / FIXTURE_FILES[kind], dest)
    return _make_source(kind, declared)


@pytest.mark.parametrize("kind", list(FIXTURE_FILES))
def test_parser_emits_expected_statement_count(tmp_path: Path, kind: str) -> None:
    """Every declared source kind produces the expected statement count from its fixture."""
    if kind == "policy_doc":
        source = _stage(tmp_path, kind, path="docs/policy.md")
    else:
        source = _stage(tmp_path, kind)

    parsed = parse_instruction_source(source, base_dir=tmp_path)

    assert parsed.source_kind == kind
    assert parsed.path == source.path
    assert len(parsed.statements) == EXPECTED_STATEMENT_COUNT[kind], (
        f"unexpected statement count for {kind}: {[s.text for s in parsed.statements]}"
    )


def test_markdown_parser_skips_code_fences(tmp_path: Path) -> None:
    """Lines inside ``` code fences must not appear in extracted statements."""
    source = _stage(tmp_path, "agents_md")
    parsed = parse_instruction_source(source, base_dir=tmp_path)
    texts = [s.text for s in parsed.statements]
    assert all("craik run execute --role" not in t for t in texts), (
        "code-fence content leaked into statements"
    )


def test_markdown_parser_records_line_ranges(tmp_path: Path) -> None:
    """Statements carry 1-indexed line ranges matching the source bytes."""
    source = _stage(tmp_path, "agents_md")
    parsed = parse_instruction_source(source, base_dir=tmp_path)
    first = parsed.statements[0]
    raw = (tmp_path / source.path).read_text(encoding="utf-8").splitlines()
    assert first.start_line >= 1
    assert first.end_line >= first.start_line
    # The actual fixture line at start_line-1 (0-indexed) must contain the bullet body.
    assert "Always run" in raw[first.start_line - 1]


def test_cursor_rules_parser_skips_comments_and_blanks(tmp_path: Path) -> None:
    """Cursor-rules parser drops lines starting with '#' and empty lines."""
    source = _stage(tmp_path, "cursor_rules")
    parsed = parse_instruction_source(source, base_dir=tmp_path)
    texts = [s.text for s in parsed.statements]
    assert all(not t.lstrip().startswith("#") for t in texts)
    assert all(t.strip() for t in texts)
    assert "Never push directly to main." in texts


def test_policy_doc_accepts_arbitrary_declared_path(tmp_path: Path) -> None:
    """policy_doc has no canonical path; parser respects the registered path."""
    source = _stage(tmp_path, "policy_doc", path="docs/runtime-policy.md")
    parsed = parse_instruction_source(source, base_dir=tmp_path)
    assert parsed.path == "docs/runtime-policy.md"
    assert len(parsed.statements) == EXPECTED_STATEMENT_COUNT["policy_doc"]


def test_missing_path_raises_typed_error(tmp_path: Path) -> None:
    """Missing files surface InstructionIngestionError, not OSError."""
    source = _make_source("agents_md", "AGENTS.md")
    with pytest.raises(InstructionIngestionError) as exc:
        parse_instruction_source(source, base_dir=tmp_path)
    assert "AGENTS.md" in str(exc.value)


def test_parser_is_deterministic(tmp_path: Path) -> None:
    """Parsing the same source twice returns byte-identical statement data."""
    source = _stage(tmp_path, "agents_md")
    first = parse_instruction_source(source, base_dir=tmp_path)
    second = parse_instruction_source(source, base_dir=tmp_path)
    assert first.raw_bytes == second.raw_bytes
    assert [s.text for s in first.statements] == [s.text for s in second.statements]
    assert [s.start_line for s in first.statements] == [
        s.start_line for s in second.statements
    ]


def test_parser_preserves_raw_bytes_exactly(tmp_path: Path) -> None:
    """raw_bytes round-trips the file content unchanged for downstream hashing."""
    source = _stage(tmp_path, "agents_md")
    parsed = parse_instruction_source(source, base_dir=tmp_path)
    on_disk = (tmp_path / source.path).read_bytes()
    assert parsed.raw_bytes == on_disk
