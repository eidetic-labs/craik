"""Check release-process documentation required for package readiness."""

from __future__ import annotations

import ast
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

STORE_WRITER_EXEMPTIONS = {
    "src/craik/runtime/store/memory.py": {
        "put_assumption": (
            "legacy direct-store API; assumptions are persisted through fixtures/tests"
        ),
    },
    "src/craik/runtime/store/work.py": {
        "put_capability_grant": (
            "legacy direct-store API; grant orchestration is still runtime-facing"
        ),
    },
}

AUTH_EXEMPT_CLI_COMMANDS = {
    ("src/craik/cli_auth.py", "login"): (
        "bootstrap command; it creates the operator session required by auth-gated commands"
    ),
    ("src/craik/cli_auth.py", "logout"): (
        "bootstrap command; operators must be able to clear a stale or missing session"
    ),
    ("src/craik/cli_auth.py", "whoami"): (
        "session introspection command; it reports missing sessions without requiring one first"
    ),
    ("src/craik/cli_demos.py", "demo_persistent_agent"): (
        "deterministic demo uses fixture identity and is hardened separately "
        "from real agent commands"
    ),
    ("src/craik/cli_demos.py", "demo_stigmem_docs"): (
        "onboarding demo uses fixture-local state before an operator session exists; "
        "CRAIK_LIVE=1 provider transport is separately operator-session gated"
    ),
    ("src/craik/cli_onboarding.py", "onboard"): (
        "first-run bootstrap command that may execute before operator login is configured"
    ),
    ("src/craik/cli_operations.py", "policy_test"): (
        "deterministic release/security baseline run by CI before operator login exists"
    ),
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
    failures.extend(_cli_auth_coverage_failures())

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
    store_dir = ROOT / "src/craik/runtime/store"
    if not store_dir.exists():
        return []
    store_paths = sorted(
        path
        for path in store_dir.glob("*.py")
        if path.name not in {"__init__.py", "base.py"}
    )
    production_files = [
        path
        for path in (ROOT / "src").rglob("*.py")
        if path not in store_paths and "__pycache__" not in path.parts
    ]
    failures: list[str] = []
    for store_path in store_paths:
        relative_path = store_path.relative_to(ROOT).as_posix()
        writer_names = _store_writer_names(store_path)
        for writer_name in writer_names:
            if writer_name in STORE_WRITER_EXEMPTIONS.get(relative_path, {}):
                continue
            needle = f".{writer_name}("
            if not any(needle in path.read_text(encoding="utf-8") for path in production_files):
                failures.append(f"{relative_path}: {writer_name} has no production caller")
    return failures


def _store_writer_names(path: Path) -> list[str]:
    return sorted(
        {
            line.strip().split("(", 1)[0].removeprefix("def ")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("def put_")
        }
    )


def _cli_auth_coverage_failures() -> list[str]:
    """Fail when an operator CLI command reads local state without auth."""
    failures: list[str] = []
    for path in _cli_command_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in (item for item in tree.body if isinstance(item, ast.FunctionDef)):
            if not _has_command_decorator(node):
                continue
            if not _touches_local_store(node):
                continue
            if _is_auth_exempt(path, node.name):
                continue
            if not _calls_operator_auth(node):
                failures.append(
                    f"{path.relative_to(ROOT)}: command `{node.name}` touches LocalStore "
                    "without operator_identity_or_fail()"
                )
    return failures


def _cli_command_paths() -> list[Path]:
    return sorted(
        {
            path
            for pattern in ("cli.py", "cli_*.py")
            for path in (ROOT / "src/craik").glob(pattern)
        }
    )


def _is_auth_exempt(path: Path, command_name: str) -> bool:
    return (path.relative_to(ROOT).as_posix(), command_name) in AUTH_EXEMPT_CLI_COMMANDS


def _has_command_decorator(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        if call is None:
            continue
        function = call.func
        if isinstance(function, ast.Attribute) and function.attr == "command":
            return True
    return False


def _touches_local_store(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "LocalStore":
            return True
        if isinstance(child, ast.Attribute) and child.attr in {
            "initialize",
            "list_projects",
            "get_contract",
        }:
            return True
    return False


def _calls_operator_auth(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            function = child.func
            if isinstance(function, ast.Name) and function.id in {
                "operator_identity_or_fail",
                "_operator_identity",
            }:
                return True
            if isinstance(function, ast.Attribute) and function.attr in {
                "operator_identity_or_fail",
                "_operator_identity",
            }:
                return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
