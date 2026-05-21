"""Check release-process documentation required for package readiness."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STATIC_REQUIRED_TERMS = {
    "CHANGELOG.md": [
        "# Changelog",
        "## Unreleased",
        "0.x.0",
    ],
    "docs/guides/release-management.md": [
        "# Release Management",
        "0.x.0",
        "Tag Policy",
        "Release Notes",
        "PyPI",
        "Protected Environment",
    ],
    "docs/security/release-process.md": [
        "# Security Release Process",
        "Security Patch Flow",
        "Private Coordination",
        "Disclosure",
        "Post-Release Verification",
    ],
}


def main() -> int:
    version = _project_version()
    failures: list[str] = []
    for relative_path, required_terms in STATIC_REQUIRED_TERMS.items():
        path = ROOT / relative_path
        if not path.exists():
            failures.append(f"{relative_path}: missing file")
            continue

        content = path.read_text(encoding="utf-8")
        missing_terms = [term for term in required_terms if term not in content]
        if missing_terms:
            failures.append(f"{relative_path}: missing {', '.join(missing_terms)}")

    changelog = ROOT / "CHANGELOG.md"
    if changelog.exists() and f"## {version}" not in changelog.read_text(encoding="utf-8"):
        failures.append(f"CHANGELOG.md: missing section for current version {version}")

    failures.extend(_extension_writer_call_failures())

    if failures:
        print("Release readiness checks failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Release readiness docs are present.")
    return 0


def _project_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _extension_writer_call_failures() -> list[str]:
    extension_path = ROOT / "src/craik/runtime/store/extensions.py"
    if not extension_path.exists():
        return []
    writer_names = sorted(
        {
            line.strip().split("(", 1)[0].removeprefix("def ")
            for line in extension_path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("def put_")
        }
    )
    production_files = [
        path
        for path in (ROOT / "src").rglob("*.py")
        if path != extension_path and "__pycache__" not in path.parts
    ]
    failures: list[str] = []
    for writer_name in writer_names:
        needle = f".{writer_name}("
        if not any(needle in path.read_text(encoding="utf-8") for path in production_files):
            failures.append(
                f"src/craik/runtime/store/extensions.py: {writer_name} has no production caller"
            )
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
