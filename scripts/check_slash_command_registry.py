"""Validate slash command schema metadata against runtime dispatch."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.runtime.shell.slash_command_schema import (  # noqa: E402
    SlashCommandSpec,
    slash_command_specs,
)
from craik.runtime.shell.slash_commands import list_slash_commands  # noqa: E402


def main() -> int:
    failures = registry_failures(slash_command_specs())
    if failures:
        print("Slash command registry checks failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Slash command registry checks passed.")
    return 0


def registry_failures(specs: Iterable[SlashCommandSpec]) -> list[str]:
    """Return schema/dispatch consistency failures."""
    spec_list = list(specs)
    runtime_commands = list_slash_commands()
    spec_names = [spec.command_name for spec in spec_list]
    runtime_names = [command.name for command in runtime_commands]
    failures: list[str] = []

    failures.extend(_duplicate_failures(spec_names, "command spec"))
    failures.extend(_duplicate_failures(runtime_names, "runtime command"))

    missing_runtime = sorted(set(spec_names) - set(runtime_names))
    if missing_runtime:
        failures.append(
            "schema entries without runtime commands: " + ", ".join(missing_runtime)
        )

    missing_schema = sorted(set(runtime_names) - set(spec_names))
    if missing_schema:
        failures.append(
            "runtime commands without schema entries: " + ", ".join(missing_schema)
        )

    runtime_by_name = {command.name: command for command in runtime_commands}
    for spec in spec_list:
        command = runtime_by_name.get(spec.command_name)
        if command is None:
            continue
        if spec.empty_state is None:
            failures.append(f"/{spec.command_name}: missing empty-state guidance")
        if command.usage != spec.usage:
            failures.append(
                f"/{spec.command_name}: runtime usage {command.usage!r} "
                f"does not match schema usage {spec.usage!r}"
            )
        if command.summary != spec.summary:
            failures.append(
                f"/{spec.command_name}: runtime summary does not match schema summary"
            )
        if command.aliases != spec.aliases:
            failures.append(
                f"/{spec.command_name}: runtime aliases {command.aliases!r} "
                f"do not match schema aliases {spec.aliases!r}"
            )
        if command.mutating != spec.mutating:
            failures.append(
                f"/{spec.command_name}: runtime mutating={command.mutating!r} "
                f"does not match schema mutating={spec.mutating!r}"
            )
        if command.readiness != spec.readiness:
            failures.append(
                f"/{spec.command_name}: runtime readiness={command.readiness!r} "
                f"does not match schema readiness={spec.readiness!r}"
            )

    return failures


def _duplicate_failures(values: list[str], label: str) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if not duplicates:
        return []
    return [f"duplicate {label} names: {', '.join(sorted(duplicates))}"]


if __name__ == "__main__":
    raise SystemExit(main())
