"""Help rendering helpers for slash command schema metadata."""

from __future__ import annotations

from craik.runtime.shell.slash_command_schema import SlashCommandSpec


def argument_help_markdown(spec: SlashCommandSpec) -> str:
    """Return Markdown help for a command with missing or invalid arguments."""
    lines = [
        f"# {spec.name}",
        "",
        spec.summary,
        "",
        f"Usage: `{spec.usage}`",
    ]
    if spec.required_args:
        lines.extend(("", "Required arguments:", *[f"- `{arg}`" for arg in spec.required_args]))
    if spec.choices:
        lines.append("")
        lines.append("Choices:")
        for name, values in spec.choices.items():
            lines.append(f"- `{name}`: " + ", ".join(f"`{value}`" for value in values))
    if spec.examples:
        lines.extend(("", "Examples:", *[f"- `{example}`" for example in spec.examples]))
    return "\n".join(lines)
