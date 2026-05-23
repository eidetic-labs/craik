"""Reject private comparison-brand language from public codebase artifacts.

This guard allows existing technical runner/provider identifiers such as
``codex`` or ``claude`` when they are API contracts, but blocks public
comparison or positioning phrases that belong only in private planning notes.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "scripts" / "_brand_hygiene_allowlist.txt"
ALLOWLIST_CAP = 5

_FORBIDDEN_BRAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bCodex CLI\b", re.IGNORECASE),
        "private comparison reference",
    ),
    (
        re.compile(r"\bClaude Code\b", re.IGNORECASE),
        "private comparison reference",
    ),
    (
        re.compile(r"\bChatGPT\b", re.IGNORECASE),
        "consumer-product comparison reference",
    ),
    (
        re.compile(r"\bOpenClaw\b", re.IGNORECASE),
        "private competitor reference",
    ),
    (
        re.compile(r"\bHermes Agent\b", re.IGNORECASE),
        "private competitor reference",
    ),
    (
        re.compile(r"\bAider\b", re.IGNORECASE),
        "private competitor reference",
    ),
    (
        re.compile(r"\bCopilot CLI\b", re.IGNORECASE),
        "private competitor reference",
    ),
    (
        re.compile(
            r"\b(Codex|Claude|ChatGPT|Aider)[-\s](style|shape|like|inspired)\b",
            re.IGNORECASE,
        ),
        "comparison-shape phrasing",
    ),
)

_SCAN_ROOTS = (
    Path("src/craik"),
    Path("tests"),
    Path("docs"),
)
_SCAN_FILES = (
    Path("README.md"),
    Path("CHANGELOG.md"),
    Path("SECURITY.md"),
)
_SCAN_SUFFIXES = {".py", ".tcss", ".md", ".js", ".jsx", ".ts", ".tsx"}


@dataclass(frozen=True)
class BrandHygieneAllowlistEntry:
    """One documented brand-hygiene exception."""

    path: str
    line_number: int
    reason: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    failures = codebase_brand_hygiene_failures(args.root)
    if failures:
        print("Codebase brand hygiene checks failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Codebase brand hygiene checks passed.")
    return 0


def codebase_brand_hygiene_failures(root: Path = ROOT) -> list[str]:
    """Return public-artifact brand-hygiene failures under ``root``."""
    failures = _allowlist_contract_failures(root)
    allowlist = _brand_hygiene_allowlist(root)
    allowed_locations = {(entry.path, entry.line_number) for entry in allowlist}
    for path in _iter_scanned_paths(root):
        relative_path = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern, description in _FORBIDDEN_BRAND_PATTERNS:
            for match in pattern.finditer(content):
                line_number = content[: match.start()].count("\n") + 1
                if (relative_path, line_number) in allowed_locations:
                    continue
                failures.append(
                    f"{relative_path}:{line_number}: forbidden brand reference "
                    f"{match.group()!r} ({description})"
                )
    return failures


def _iter_scanned_paths(root: Path = ROOT) -> list[Path]:
    paths: list[Path] = []
    for relative_root in _SCAN_ROOTS:
        scan_root = root / relative_root
        if not scan_root.exists():
            continue
        paths.extend(
            path
            for path in scan_root.rglob("*")
            if path.is_file()
            and path.suffix in _SCAN_SUFFIXES
            and "__pycache__" not in path.parts
            and "build" not in path.parts
            and "node_modules" not in path.parts
        )
    paths.extend(path for relative in _SCAN_FILES if (path := root / relative).exists())
    return sorted(paths)


def _allowlist_contract_failures(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    allowlist_path = root / ALLOWLIST_PATH.relative_to(ROOT)
    if not allowlist_path.exists():
        return [f"{allowlist_path.relative_to(root)}: missing allowlist file"]
    entries = _brand_hygiene_allowlist(root)
    if len(entries) > ALLOWLIST_CAP:
        failures.append(
            f"{allowlist_path.relative_to(root)}: allowlist has {len(entries)} "
            f"entries; cap is {ALLOWLIST_CAP}"
        )
    for entry in entries:
        if not entry.reason.strip():
            failures.append(
                f"{allowlist_path.relative_to(root)}: {entry.path}:{entry.line_number} "
                "is missing a rationale"
            )
    return failures


def _brand_hygiene_allowlist(root: Path = ROOT) -> list[BrandHygieneAllowlistEntry]:
    allowlist_path = root / ALLOWLIST_PATH.relative_to(ROOT)
    if not allowlist_path.exists():
        return []
    entries: list[BrandHygieneAllowlistEntry] = []
    for raw_line in allowlist_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "| reason:" not in line:
            entries.append(BrandHygieneAllowlistEntry(line, 0, ""))
            continue
        location, reason = line.split("| reason:", 1)
        path_text, _, line_text = location.strip().rpartition(":")
        try:
            line_number = int(line_text)
        except ValueError:
            line_number = 0
        entries.append(
            BrandHygieneAllowlistEntry(
                path=path_text.strip(),
                line_number=line_number,
                reason=reason.strip(),
            )
        )
    return entries


if __name__ == "__main__":
    raise SystemExit(main())
