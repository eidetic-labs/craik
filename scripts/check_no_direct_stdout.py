"""Guard migrated CLI/TUI shared commands against direct stdout writes.

The guard is intentionally ratcheted: commands enter
STRICT_COMMAND_RESULT_RENDERING once their Typer output is emitted through
``emit_command_result`` and their slash output is supplied only by
``CommandResult``. This keeps converted commands from regressing while the
remaining v0.12.8 migration continues.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "craik"

STRICT_COMMAND_RESULT_RENDERING: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/craik/cli_auth.py", "auth_add"),
        ("src/craik/cli_auth.py", "auth_approve"),
        ("src/craik/cli_auth.py", "auth_grant"),
        ("src/craik/cli_auth.py", "auth_list"),
        ("src/craik/cli_auth.py", "auth_remove"),
        ("src/craik/cli_auth.py", "auth_setup"),
        ("src/craik/cli_auth.py", "auth_status"),
        ("src/craik/cli_auth.py", "auth_test"),
        ("src/craik/cli_auth.py", "logout"),
        ("src/craik/cli_auth.py", "whoami"),
        ("src/craik/cli_auth_login.py", "auth_logout_provider"),
        ("src/craik/cli_auth_login.py", "auth_migrate_from_env"),
        ("src/craik/cli_auth_login.py", "auth_migrate_secrets"),
        ("src/craik/cli_auth_login.py", "auth_storage_status"),
        ("src/craik/cli_agent_messages.py", "agent_message_receive"),
        ("src/craik/cli_agent_messages.py", "agent_message_send"),
        ("src/craik/cli_connect.py", "connect_stigmem"),
        ("src/craik/cli_delegations.py", "delegation_pause"),
        ("src/craik/cli_delegations.py", "delegation_resolve"),
        ("src/craik/cli_migration.py", "migrate_import"),
        ("src/craik/cli_migration.py", "migrate_inspect"),
        ("src/craik/cli_migration.py", "migrate_plan"),
        ("src/craik/cli_migration.py", "migrate_report"),
        ("src/craik/cli_onboarding.py", "onboard"),
        ("src/craik/cli_references.py", "references_list"),
        ("src/craik/cli_references.py", "references_verify"),
        ("src/craik/cli_review.py", "review_critic"),
        ("src/craik/cli_review.py", "review_red_team"),
        ("src/craik/cli_scope_changes.py", "scope_change_decide"),
        ("src/craik/cli_session_portability.py", "session_export_portable"),
        ("src/craik/cli_session_portability.py", "session_import_portable"),
        ("src/craik/cli_operator_continuity.py", "operator_run_delta"),
        ("src/craik/cli_operator_continuity.py", "operator_traps"),
        ("src/craik/cli_tasks.py", "task_resume"),
    }
)

_DIRECT_STDOUT_NAMES = {"print"}
_DIRECT_STDOUT_ATTRS = {
    ("typer", "echo"),
    ("sys.stdout", "write"),
    ("console", "print"),
}


def main() -> int:
    failures = direct_stdout_failures(ROOT)
    if failures:
        print("Direct stdout guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Direct stdout guard passed.")
    return 0


def direct_stdout_failures(root: Path) -> list[str]:
    """Return direct stdout violations for strict shared command callbacks."""
    failures: list[str] = []
    for path in sorted((root / "src" / "craik").glob("cli*.py")):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            key = (relative, node.name)
            if key not in STRICT_COMMAND_RESULT_RENDERING:
                continue
            if not _has_craik_command_decorator(node):
                failures.append(
                    f"{relative}:{node.lineno} {node.name} is strict "
                    "but lacks @craik_command"
                )
                continue
            calls = _direct_stdout_calls(node)
            for call in calls:
                failures.append(
                    f"{relative}:{call.lineno} {node.name} writes directly to stdout; "
                    "use craik.cli_output.emit_command_result(result)"
                )
    return failures


def _has_craik_command_decorator(node: ast.FunctionDef) -> bool:
    return any(_decorator_name(decorator) == "craik_command" for decorator in node.decorator_list)


def _decorator_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _callable_name(node.func)
    return _callable_name(node)


def _direct_stdout_calls(node: ast.FunctionDef) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = _callable_name(child.func)
        if name in _DIRECT_STDOUT_NAMES:
            calls.append(child)
            continue
        if name is None:
            continue
        parts = name.rsplit(".", 1)
        if len(parts) == 2 and (parts[0], parts[1]) in _DIRECT_STDOUT_ATTRS:
            calls.append(child)
    return calls


def _callable_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _callable_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


if __name__ == "__main__":
    raise SystemExit(main())
