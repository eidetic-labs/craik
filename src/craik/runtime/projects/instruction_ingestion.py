"""Parsers for declared instruction source files (issue #606).

This module reads declared instruction-source files from disk and produces
typed intermediate records (``ParsedInstructionSource`` with a sequence of
``InstructionStatement``) that downstream slices consume:

* #607 — computes ``InstructionSourceSnapshot`` from ``raw_bytes``.
* #608 — extracts ``InstructionProvenance`` records from each statement's
  ``start_line`` / ``end_line`` / column ranges.
* #609 — categorizes each statement and assembles
  ``DistilledInstructionProposal`` records.

The parsers themselves are pure: they read exactly one file (relative to a
project base directory), perform no store writes, and return the same output
for the same input bytes. They distinguish two source families:

* **Markdown-style** sources where instructions live in bulleted lists under
  level-2+ headings. Used for AGENTS.md, CLAUDE.md, GEMINI.md, HERMES.md,
  SKILLS.md, the GitHub Copilot instructions file, and the Codex instructions
  file.
* **Policy document** sources where the declared Markdown file is captured as
  one free-form statement block.
* **Cursor-rules style** sources where every non-empty, non-comment line is
  one statement. Used for ``.cursorrules``.

Detection order follows ``InstructionSource.kind`` exactly; callers never
need to sniff content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from craik.contracts.models import InstructionSource, InstructionSourceKind

_MARKDOWN_KINDS: frozenset[InstructionSourceKind] = frozenset(
    {
        "agents_md",
        "claude_md",
        "gemini_md",
        "hermes_md",
        "skills_md",
        "github_copilot_instructions",
        "codex_instructions",
    }
)
_CURSOR_KINDS: frozenset[InstructionSourceKind] = frozenset({"cursor_rules"})

_BULLET_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d+\.)\s+(?P<text>.+?)\s*$")
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*```")


class InstructionIngestionError(RuntimeError):
    """Raised when a declared instruction source cannot be read or parsed."""


@dataclass(frozen=True)
class InstructionStatement:
    """One instruction candidate identified by a parser.

    Line and column offsets are 1-indexed and inclusive.
    """

    text: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    section_label: str | None = None


@dataclass(frozen=True)
class ParsedInstructionSource:
    """Parser output for one declared instruction source."""

    source_kind: InstructionSourceKind
    path: str
    raw_bytes: bytes
    statements: tuple[InstructionStatement, ...] = field(default_factory=tuple)


def parse_instruction_source(
    source: InstructionSource, *, base_dir: Path
) -> ParsedInstructionSource:
    """Read and parse a declared instruction source from disk.

    The file is resolved as ``base_dir / source.path``. Missing files raise
    :class:`InstructionIngestionError` so callers can surface operator
    guidance instead of an opaque OSError.
    """
    root = base_dir.resolve()
    abs_path = (root / source.path).resolve()
    try:
        abs_path.relative_to(root)
    except ValueError as exc:
        raise InstructionIngestionError(
            f"instruction source path escapes project root: {source.path}"
        ) from exc
    if not abs_path.exists():
        raise InstructionIngestionError(
            f"instruction source path does not exist: {source.path}"
        )
    if not abs_path.is_file():
        raise InstructionIngestionError(
            f"instruction source path is not a file: {source.path}"
        )
    try:
        raw_bytes = abs_path.read_bytes()
    except OSError as exc:
        raise InstructionIngestionError(
            f"failed to read instruction source {source.path}: {exc}"
        ) from exc

    if source.kind in _MARKDOWN_KINDS:
        statements = _parse_markdown(raw_bytes)
    elif source.kind == "policy_doc":
        statements = _parse_policy_doc(raw_bytes)
    elif source.kind in _CURSOR_KINDS:
        statements = _parse_cursor_rules(raw_bytes)
    else:  # pragma: no cover - exhaustive over the InstructionSourceKind literal
        raise InstructionIngestionError(
            f"no parser registered for instruction source kind: {source.kind}"
        )

    return ParsedInstructionSource(
        source_kind=source.kind,
        path=source.path,
        raw_bytes=raw_bytes,
        statements=statements,
    )


def _decode(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstructionIngestionError(
            f"instruction source is not valid UTF-8: {exc}"
        ) from exc


def _parse_markdown(raw_bytes: bytes) -> tuple[InstructionStatement, ...]:
    """Extract one statement per bullet line under non-fenced markdown."""
    text = _decode(raw_bytes)
    lines = text.splitlines()
    statements: list[InstructionStatement] = []
    section_label: str | None = None
    in_fence = False

    for index, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            section_label = heading.group("title").strip()
            continue

        bullet = _BULLET_RE.match(line)
        if not bullet:
            continue

        statement_text = bullet.group("text").strip()
        if not statement_text:
            continue

        # Columns are 1-indexed positions of the first/last character of the
        # extracted text within the source line.
        text_start = line.find(statement_text)
        start_column = text_start + 1 if text_start >= 0 else 1
        end_column = start_column + len(statement_text) - 1

        statements.append(
            InstructionStatement(
                text=statement_text,
                start_line=index,
                end_line=index,
                start_column=start_column,
                end_column=end_column,
                section_label=section_label,
            )
        )
    return tuple(statements)


def _parse_cursor_rules(raw_bytes: bytes) -> tuple[InstructionStatement, ...]:
    """Treat every non-empty, non-comment line as one cursor-rules statement."""
    text = _decode(raw_bytes)
    statements: list[InstructionStatement] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        text_start = line.find(stripped)
        start_column = text_start + 1 if text_start >= 0 else 1
        end_column = start_column + len(stripped) - 1
        statements.append(
            InstructionStatement(
                text=stripped,
                start_line=index,
                end_line=index,
                start_column=start_column,
                end_column=end_column,
            )
        )
    return tuple(statements)


def _parse_policy_doc(raw_bytes: bytes) -> tuple[InstructionStatement, ...]:
    """Treat a declared policy document as one free-form statement block."""
    text = _decode(raw_bytes)
    lines = text.splitlines()
    first_line: int | None = None
    last_line: int | None = None
    for index, line in enumerate(lines, start=1):
        if line.strip():
            first_line = index if first_line is None else first_line
            last_line = index
    if first_line is None or last_line is None:
        return ()

    statement_text = "\n".join(lines[first_line - 1 : last_line]).strip()
    first_source_line = lines[first_line - 1]
    last_source_line = lines[last_line - 1]
    first_stripped = first_source_line.lstrip()
    last_stripped = last_source_line.rstrip()
    start_column = len(first_source_line) - len(first_stripped) + 1
    end_column = len(last_stripped)
    return (
        InstructionStatement(
            text=statement_text,
            start_line=first_line,
            end_line=last_line,
            start_column=start_column,
            end_column=end_column,
        ),
    )


__all__ = [
    "InstructionIngestionError",
    "InstructionStatement",
    "ParsedInstructionSource",
    "parse_instruction_source",
]
