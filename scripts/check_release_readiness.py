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

REGISTRY_DISPATCHED_CALLABLES: dict[str, str] = {
    # qualified.name: "rationale (file:line of registration site)"
}

STORE_WRITER_ENTRYPOINT_PREFIXES = (
    "src/craik/runtime/agents/",
    "src/craik/runtime/channels/webhook_ingress.py",
    "src/craik/runtime/companions/",
    "src/craik/runtime/dashboard/",
    "src/craik/runtime/gateway.py",
    "src/craik/runtime/memory/",
    "src/craik/runtime/memory/freshness.py",
    "src/craik/runtime/projects/",
    "src/craik/runtime/providers/",
    "src/craik/runtime/reviewing/",
    "src/craik/runtime/runners/",
    "src/craik/runtime/shell/",
    "src/craik/runtime/skills/",
    "src/craik/runtime/work/",
)

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
    ("src/craik/cli_auth_login.py", "auth_login_provider"): (
        "provider credential bootstrap command; it captures provider credentials before "
        "an operator session may exist"
    ),
    ("src/craik/cli_auth_login.py", "auth_migrate_from_env"): (
        "one-time provider credential migration command; it runs during auth bootstrap"
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
    reachable_calls = _reachable_production_call_names(production_files)
    writer_definitions = _store_writer_definitions(store_paths)
    writer_name_counts: dict[str, int] = {}
    for writer_name in writer_definitions.values():
        writer_name_counts[writer_name] = writer_name_counts.get(writer_name, 0) + 1
    failures: list[str] = []
    for writer_qualname, writer_name in writer_definitions.items():
        store_path = _path_from_module_qualname(writer_qualname.rsplit(".", 1)[0])
        relative_path = store_path.relative_to(ROOT).as_posix()
        if writer_qualname in REGISTRY_DISPATCHED_CALLABLES:
            continue
        if writer_qualname in reachable_calls:
            continue
        if writer_name_counts[writer_name] == 1 and f"*.{writer_name}" in reachable_calls:
            continue
        if writer_name in STORE_WRITER_EXEMPTIONS.get(relative_path, {}):
            continue
        failures.append(f"{relative_path}: {writer_qualname} has no production caller")
    failures.extend(_registry_dispatched_callable_failures())
    return failures


def _store_writer_definitions(paths: list[Path]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for path in paths:
        module_qualname = _module_qualname(path)
        for writer_name in _store_writer_names(path):
            definitions[f"{module_qualname}.{writer_name}"] = writer_name
    return definitions


def _store_writer_names(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    writer_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("put_"):
            writer_names.add(node.name)
        elif isinstance(node, ast.ClassDef) and not _inherits_protocol(node):
            writer_names.update(
                item.name
                for item in node.body
                if isinstance(item, ast.FunctionDef) and item.name.startswith("put_")
            )
    return sorted(writer_names)


def _inherits_protocol(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Protocol":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Protocol":
            return True
    return False


def _registry_dispatched_callable_failures() -> list[str]:
    source_functions = _source_function_qualnames()
    failures: list[str] = []
    for qualname in REGISTRY_DISPATCHED_CALLABLES:
        if qualname not in source_functions:
            failures.append(
                f"REGISTRY_DISPATCHED_CALLABLES: {qualname} is not a real src function"
            )
    return failures


def _source_function_qualnames() -> set[str]:
    function_qualnames: set[str] = set()
    for path in (ROOT / "src").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        module_qualname = _module_qualname(path)
        for node in _function_defs(tree):
            function_qualnames.add(f"{module_qualname}.{node.name}")
    return function_qualnames


def _module_qualname(path: Path) -> str:
    return (
        path.relative_to(ROOT / "src")
        .with_suffix("")
        .as_posix()
        .replace("/", ".")
    )


def _path_from_module_qualname(module_qualname: str) -> Path:
    return ROOT / "src" / Path(module_qualname.replace(".", "/")).with_suffix(".py")


def _reachable_production_call_names(paths: list[Path]) -> set[str]:
    definitions: dict[str, set[str]] = {}
    entries: set[str] = set()
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        relative_path = path.relative_to(ROOT).as_posix()
        module_qualname = _module_qualname(path)
        local_function_names = {node.name for node in _function_defs(tree)}
        import_map = _import_aliases(tree)
        for node in _function_defs(tree):
            function_qualname = f"{module_qualname}.{node.name}"
            definitions.setdefault(function_qualname, set()).update(
                _called_names(
                    node,
                    current_module=module_qualname,
                    import_map=import_map,
                    local_function_names=local_function_names,
                )
            )
            if _has_command_decorator(node) or _is_writer_entrypoint(relative_path):
                entries.add(function_qualname)

    reachable_functions = set(entries)
    reachable_calls: set[str] = set()
    pending = list(entries)
    definitions_by_bare_name: dict[str, list[str]] = {}
    for function_qualname in definitions:
        bare_name = function_qualname.rsplit(".", 1)[1]
        definitions_by_bare_name.setdefault(bare_name, []).append(function_qualname)
    while pending:
        name = pending.pop()
        calls = definitions.get(name, set())
        reachable_calls.update(calls)
        for called in calls:
            targets = _definition_targets(called, definitions, definitions_by_bare_name)
            for target in targets:
                if target not in reachable_functions:
                    reachable_functions.add(target)
                    pending.append(target)
    return reachable_calls


def _definition_targets(
    called: str,
    definitions: dict[str, set[str]],
    definitions_by_bare_name: dict[str, list[str]],
) -> list[str]:
    if called in definitions:
        return [called]
    if not called.startswith("*."):
        return []
    candidates = definitions_by_bare_name.get(called.removeprefix("*."), [])
    if len(candidates) == 1:
        return candidates
    return []


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                aliases[local_name] = alias.name if alias.asname else local_name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname or alias.name
                aliases[local_name] = f"{node.module}.{alias.name}"
    return aliases


def _function_defs(tree: ast.AST) -> list[ast.FunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def _called_names(
    node: ast.FunctionDef,
    *,
    current_module: str,
    import_map: dict[str, str],
    local_function_names: set[str],
) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        function = child.func
        if isinstance(function, ast.Name):
            names.add(
                _resolve_name_call(
                    function.id,
                    current_module=current_module,
                    import_map=import_map,
                    local_function_names=local_function_names,
                )
            )
        elif isinstance(function, ast.Attribute):
            names.add(_resolve_attribute_call(function, import_map=import_map))
    return names


def _resolve_name_call(
    name: str,
    *,
    current_module: str,
    import_map: dict[str, str],
    local_function_names: set[str],
) -> str:
    if name in import_map:
        return import_map[name]
    if name in local_function_names:
        return f"{current_module}.{name}"
    return f"*.{name}"


def _resolve_attribute_call(function: ast.Attribute, *, import_map: dict[str, str]) -> str:
    dotted_name = _dotted_name(function)
    if dotted_name is None:
        return f"*.{function.attr}"
    parts = dotted_name.split(".")
    for index in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:index])
        suffix = ".".join(parts[index:])
        if prefix in import_map:
            return f"{import_map[prefix]}.{suffix}"
    if parts[0] in import_map:
        return ".".join([import_map[parts[0]], *parts[1:]])
    if dotted_name.startswith("craik."):
        return dotted_name
    return f"*.{function.attr}"


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent is None:
            return None
        return f"{parent}.{node.attr}"
    return None


def _is_writer_entrypoint(relative_path: str) -> bool:
    return any(relative_path.startswith(prefix) for prefix in STORE_WRITER_ENTRYPOINT_PREFIXES)


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
