"""Coverage guard for registered slash-command dispatch paths."""

from __future__ import annotations

from pathlib import Path

from craik.runtime.shell.slash_command_schema import SlashCommandSpec, slash_command_specs
from craik.runtime.shell.slash_commands import dispatch_slash_command

FORBIDDEN_INLINE_FALLBACKS = (
    "registered but has no inline handler",
    "Use `craik ",
    "run `craik ",
)


def test_registered_slash_usage_and_examples_dispatch_inline(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "craik-home")}

    failures: list[tuple[str, str]] = []
    for spec in slash_command_specs():
        for command in _commands_for_spec(spec):
            result = dispatch_slash_command(command, env=env)
            if any(phrase in result.text for phrase in FORBIDDEN_INLINE_FALLBACKS):
                failures.append((command, result.text))

    assert failures == []


def _commands_for_spec(spec: SlashCommandSpec) -> list[str]:
    commands = [spec.usage]
    if spec.example:
        commands.append(spec.example)
    commands.extend(spec.examples)
    return list(dict.fromkeys(commands))
