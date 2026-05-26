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
        ("src/craik/cli_auth_login.py", "auth_login_provider"),
        ("src/craik/cli.py", "dashboard_command"),
        ("src/craik/cli.py", "desktop_action_command"),
        ("src/craik/cli.py", "desktop_menu_command"),
        ("src/craik/cli.py", "desktop_notify_approval_command"),
        ("src/craik/cli.py", "desktop_status_command"),
        ("src/craik/cli.py", "desktop_update_check_command"),
        ("src/craik/cli.py", "schema_list"),
        ("src/craik/cli.py", "schema_show"),
        ("src/craik/cli.py", "setup_command"),
        ("src/craik/cli_auth_login.py", "auth_logout_provider"),
        ("src/craik/cli_auth_login.py", "auth_migrate_from_env"),
        ("src/craik/cli_auth_login.py", "auth_migrate_secrets"),
        ("src/craik/cli_auth_login.py", "auth_storage_status"),
        ("src/craik/cli_agent_messages.py", "agent_message_receive"),
        ("src/craik/cli_agent_messages.py", "agent_message_send"),
        ("src/craik/cli_agents.py", "agent_launch"),
        ("src/craik/cli_agents.py", "agent_list"),
        ("src/craik/cli_agents.py", "agent_prompt"),
        ("src/craik/cli_agents.py", "agent_recover"),
        ("src/craik/cli_agents.py", "agent_rename"),
        ("src/craik/cli_agents.py", "agent_restart"),
        ("src/craik/cli_agents.py", "agent_status"),
        ("src/craik/cli_agents.py", "agent_stop"),
        ("src/craik/cli_channels.py", "channel_doctor_command"),
        ("src/craik/cli_channels.py", "channel_fixture_schema_command"),
        ("src/craik/cli_channels.py", "channel_list_command"),
        ("src/craik/cli_channels.py", "channel_normalize_fixture_command"),
        ("src/craik/cli_channels.py", "channel_respond_fixture_command"),
        ("src/craik/cli_channels.py", "channel_setup_command"),
        ("src/craik/cli_connect.py", "connect_stigmem"),
        ("src/craik/cli_delegations.py", "delegation_pause"),
        ("src/craik/cli_delegations.py", "delegation_resolve"),
        ("src/craik/cli_demos.py", "demo_persistent_agent"),
        ("src/craik/cli_demos.py", "demo_stigmem_docs"),
        ("src/craik/cli_instructions.py", "instructions_approve"),
        ("src/craik/cli_instructions.py", "instructions_ingest"),
        ("src/craik/cli_instructions.py", "instructions_list"),
        ("src/craik/cli_instructions.py", "instructions_register"),
        ("src/craik/cli_instructions.py", "instructions_reject"),
        ("src/craik/cli_instructions.py", "instructions_show"),
        ("src/craik/cli_knowledge.py", "knowledge_context_request"),
        ("src/craik/cli_knowledge.py", "knowledge_fulfill_context_request"),
        ("src/craik/cli_knowledge.py", "knowledge_negative"),
        ("src/craik/cli_knowledge.py", "knowledge_resolve_context_debt"),
        ("src/craik/cli_knowledge.py", "knowledge_resolve_unknown"),
        ("src/craik/cli_knowledge.py", "knowledge_scratchpad"),
        ("src/craik/cli_knowledge.py", "knowledge_trap"),
        ("src/craik/cli_knowledge.py", "knowledge_unknown"),
        ("src/craik/cli_migration.py", "migrate_import"),
        ("src/craik/cli_migration.py", "migrate_inspect"),
        ("src/craik/cli_migration.py", "migrate_plan"),
        ("src/craik/cli_migration.py", "migrate_report"),
        ("src/craik/cli_onboarding.py", "onboard"),
        ("src/craik/cli_operations.py", "contradiction_list"),
        ("src/craik/cli_operations.py", "contradiction_open"),
        ("src/craik/cli_operations.py", "contradiction_show"),
        ("src/craik/cli_operations.py", "graph_export"),
        ("src/craik/cli_operations.py", "policy_show"),
        ("src/craik/cli_operations.py", "policy_test"),
        ("src/craik/cli_plugins.py", "plugin_grants_list"),
        ("src/craik/cli_plugins.py", "plugin_receipts_list"),
        ("src/craik/cli_plugins.py", "plugins_grant"),
        ("src/craik/cli_plugins.py", "plugins_install"),
        ("src/craik/cli_plugins.py", "plugins_probation_review"),
        ("src/craik/cli_project.py", "case_build"),
        ("src/craik/cli_project.py", "case_show"),
        ("src/craik/cli_project.py", "home_init"),
        ("src/craik/cli_project.py", "home_show"),
        ("src/craik/cli_project.py", "intent_show"),
        ("src/craik/cli_project.py", "project_add"),
        ("src/craik/cli_project.py", "project_list"),
        ("src/craik/cli_project.py", "project_show"),
        ("src/craik/cli_project.py", "prompt_compile"),
        ("src/craik/cli_project.py", "provider_list"),
        ("src/craik/cli_project.py", "provider_select"),
        ("src/craik/cli_project.py", "provider_show"),
        ("src/craik/cli_project.py", "runners_matrix"),
        ("src/craik/cli_project.py", "task_create"),
        ("src/craik/cli_references.py", "references_list"),
        ("src/craik/cli_references.py", "references_verify"),
        ("src/craik/cli_review.py", "review_critic"),
        ("src/craik/cli_review.py", "review_red_team"),
        ("src/craik/cli_runs.py", "run_cancel"),
        ("src/craik/cli_runs.py", "run_delta"),
        ("src/craik/cli_runs.py", "run_execute"),
        ("src/craik/cli_runs.py", "run_inspect"),
        ("src/craik/cli_runs.py", "run_list"),
        ("src/craik/cli_runs.py", "run_recover"),
        ("src/craik/cli_runs.py", "run_resume"),
        ("src/craik/cli_runs.py", "run_show"),
        ("src/craik/cli_scope_changes.py", "scope_change_decide"),
        ("src/craik/cli_session_portability.py", "session_export_portable"),
        ("src/craik/cli_session_portability.py", "session_import_portable"),
        ("src/craik/cli_shell.py", "insights_command"),
        ("src/craik/cli_shell.py", "model_alias"),
        ("src/craik/cli_shell.py", "model_fallback"),
        ("src/craik/cli_shell.py", "model_list"),
        ("src/craik/cli_shell.py", "model_probe"),
        ("src/craik/cli_shell.py", "model_set"),
        ("src/craik/cli_shell.py", "model_status"),
        ("src/craik/cli_shell.py", "profile_create"),
        ("src/craik/cli_shell.py", "profile_delete"),
        ("src/craik/cli_shell.py", "profile_export"),
        ("src/craik/cli_shell.py", "profile_import"),
        ("src/craik/cli_shell.py", "profile_list"),
        ("src/craik/cli_shell.py", "profile_rename"),
        ("src/craik/cli_shell.py", "profile_show"),
        ("src/craik/cli_shell.py", "profile_use"),
        ("src/craik/cli_shell.py", "rename_command"),
        ("src/craik/cli_shell.py", "session_delete"),
        ("src/craik/cli_shell.py", "session_export"),
        ("src/craik/cli_shell.py", "session_list"),
        ("src/craik/cli_shell.py", "session_prune"),
        ("src/craik/cli_shell.py", "session_rename"),
        ("src/craik/cli_shell.py", "session_resume"),
        ("src/craik/cli_shell.py", "session_show"),
        ("src/craik/cli_shell.py", "theme_command"),
        ("src/craik/cli_shell.py", "usage_command"),
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
    """Return direct stdout violations for shared command callbacks."""
    failures: list[str] = []
    for path in _cli_files(root):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if _has_tui_eligible_craik_command(node):
                for call in _direct_json_stdout_calls(node):
                    failures.append(
                        f"{relative}:{call.lineno} {node.name} emits JSON directly; "
                        "use craik.cli_output.emit_command_result(result)"
                    )
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


def _cli_files(root: Path) -> list[Path]:
    src = root / "src" / "craik"
    files = [*src.glob("cli*.py"), *(src / "cli_new").glob("*.py")]
    return sorted({path for path in files if path.is_file()})


def _has_craik_command_decorator(node: ast.FunctionDef) -> bool:
    return any(_decorator_name(decorator) == "craik_command" for decorator in node.decorator_list)


def _has_tui_eligible_craik_command(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        if _decorator_name(decorator) != "craik_command":
            continue
        if isinstance(decorator, ast.Call):
            for keyword in decorator.keywords:
                if (
                    keyword.arg == "tui_eligible"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    return False
        return True
    return False


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


def _direct_json_stdout_calls(node: ast.FunctionDef) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for call in _direct_stdout_calls(node):
        if not call.args or not isinstance(call.args[0], ast.Call):
            continue
        if _callable_name(call.args[0].func) == "json.dumps":
            calls.append(call)
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
