"""Schema metadata for Craik slash commands."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PayloadShape = Literal["table", "kv", "tree", "markdown"]
ReadinessRequirement = Literal["none", "operator", "provider", "model", "ready"]


class EmptyState(BaseModel):
    """Operator-facing empty-result copy for a slash command."""

    model_config = ConfigDict(frozen=True)

    message: str
    remediation: str | None = None


class ActionKeySet(BaseModel):
    """Canonical inline action keys supported by a slash command result."""

    model_config = ConfigDict(frozen=True)

    enter: str | None = None
    D: str | None = None
    R: str | None = None
    A: str | None = None
    F: str | None = None
    escape: str | None = None


class SlashCommandSpec(BaseModel):
    """Durable command metadata shared by slash rendering, help, and CI."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^/[a-z][a-z0-9-]*$")
    summary: str
    usage: str
    payload_shape: PayloadShape
    help: str
    example: str | None = None
    examples: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    readiness: ReadinessRequirement = "none"
    mutating: bool = False
    args_schema: str | None = None
    required_args: tuple[str, ...] = ()
    choices: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    empty_state: EmptyState | None = None
    action_keys: ActionKeySet = Field(default_factory=ActionKeySet)
    requires_confirmation: bool = False
    confirm_message: str | None = None

    @field_validator("usage")
    @classmethod
    def _usage_starts_with_command(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("usage must start with a slash command")
        return value

    @field_validator("example")
    @classmethod
    def _example_starts_with_command(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("/"):
            raise ValueError("example must start with a slash command")
        return value

    @field_validator("examples")
    @classmethod
    def _examples_start_with_command(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        invalid = [example for example in value if not example.startswith("/")]
        if invalid:
            raise ValueError("examples must start with slash commands")
        return value

    @field_validator("aliases")
    @classmethod
    def _aliases_are_bare_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        invalid = [alias for alias in value if alias.startswith("/")]
        if invalid:
            raise ValueError("aliases must not include slash prefixes")
        return value

    @property
    def command_name(self) -> str:
        """Return the command name without the leading slash."""
        return self.name.removeprefix("/")


SLASH_COMMAND_SPECS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec(
        name="/help",
        summary="Show slash-command help.",
        usage="/help [command]",
        payload_shape="markdown",
        help="Show slash-command help for all commands or one command.",
        example="/help status",
        examples=("/help status",),
    ),
    SlashCommandSpec(
        name="/setup",
        summary="Show progressive setup guidance.",
        usage="/setup",
        payload_shape="tree",
        help="Show current setup and readiness guidance.",
        empty_state=EmptyState(message="No setup actions are currently required."),
    ),
    SlashCommandSpec(
        name="/auth",
        summary="Manage operator and provider auth.",
        usage="/auth [login]",
        payload_shape="table",
        help="Inspect auth status or open provider credential capture.",
        example="/auth login",
        examples=("/auth login",),
        mutating=True,
        requires_confirmation=True,
    ),
    SlashCommandSpec(
        name="/provider",
        summary="Inspect or configure provider credentials.",
        usage="/provider [login <provider>]",
        payload_shape="table",
        help="Inspect provider credentials or open provider login capture.",
        example="/provider login openai",
        examples=("/provider login openai", "/provider login local"),
        mutating=True,
        empty_state=EmptyState(
            message="No providers are configured.",
            remediation="Run `/provider login <provider>`.",
        ),
    ),
    SlashCommandSpec(
        name="/model",
        summary="Inspect or select the active model.",
        usage="/model [set <provider/model>]",
        payload_shape="kv",
        help="Inspect model settings or select the active provider/model.",
        example="/model set openai/gpt-4o-mini",
        mutating=True,
        args_schema="model [set <provider/model>]",
    ),
    SlashCommandSpec(
        name="/status",
        summary="Show readiness state.",
        usage="/status",
        payload_shape="tree",
        help="Show operator, provider, model, and policy readiness.",
    ),
    SlashCommandSpec(
        name="/clear",
        summary="Clear the current transcript.",
        usage="/clear",
        payload_shape="markdown",
        help="Clear the current TUI transcript while preserving persisted receipts.",
        example="/clear",
        mutating=True,
        requires_confirmation=True,
        confirm_message=(
            "This discards the current session transcript from the screen. "
            "Persisted receipts and audit records remain stored."
        ),
    ),
    SlashCommandSpec(
        name="/doctor",
        summary="Run diagnostics inline.",
        usage="/doctor",
        payload_shape="tree",
        help="Run inline diagnostics for the current shell environment.",
    ),
    SlashCommandSpec(
        name="/sessions",
        summary="List persistent sessions.",
        usage="/sessions",
        payload_shape="table",
        help="List persistent sessions and the active session pointer.",
        empty_state=EmptyState(
            message="No persistent sessions found.",
            remediation="Start a prompt or run `/resume <session-id>` with a known session.",
        ),
    ),
    SlashCommandSpec(
        name="/rename",
        summary="Rename the current shell session.",
        usage="/rename <name>",
        payload_shape="kv",
        help="Rename the current shell session display name.",
        example="/rename Incident 42",
        mutating=True,
        required_args=("name",),
    ),
    SlashCommandSpec(
        name="/theme",
        summary="Inspect or switch the TUI theme.",
        usage="/theme [dark|light|monochrome]",
        payload_shape="kv",
        help="Inspect or switch the terminal UI theme.",
        example="/theme monochrome",
        mutating=True,
        choices={"theme": ("dark", "light", "monochrome")},
    ),
    SlashCommandSpec(
        name="/resume",
        summary="Resume a persistent session.",
        usage="/resume <session-id>",
        payload_shape="kv",
        help="Set the active persistent session.",
        example="/resume session_alpha",
        mutating=True,
        required_args=("session-id",),
    ),
    SlashCommandSpec(
        name="/approvals",
        summary="Inspect pending approvals.",
        usage="/approvals",
        payload_shape="table",
        help="Inspect pending approval requests.",
        empty_state=EmptyState(message="No pending approvals."),
        action_keys=ActionKeySet(enter="open", A="approve"),
    ),
    SlashCommandSpec(
        name="/handoffs",
        summary="Inspect handoffs.",
        usage="/handoffs",
        payload_shape="table",
        help="Inspect persisted handoff artifacts.",
        empty_state=EmptyState(message="No handoffs found."),
    ),
    SlashCommandSpec(
        name="/receipts",
        summary="Inspect receipts.",
        usage="/receipts [detail <receipt-id>]",
        payload_shape="table",
        help="Inspect persisted capability, plugin, and gateway receipts.",
        example="/receipts detail receipt_123",
        empty_state=EmptyState(message="No receipts found."),
        action_keys=ActionKeySet(enter="details"),
    ),
    SlashCommandSpec(
        name="/skills",
        summary="Inspect learning-loop skill controls.",
        usage="/skills",
        payload_shape="tree",
        help="Inspect learning-loop skill packages, registries, and proposals.",
        empty_state=EmptyState(message="No skill packages, registries, or proposals found."),
    ),
    SlashCommandSpec(
        name="/memory",
        summary="Inspect memory proposals and facts.",
        usage="/memory",
        payload_shape="tree",
        help="Inspect memory proposals, diffs, and impact previews.",
        empty_state=EmptyState(message="No memory proposals or diffs found."),
    ),
    SlashCommandSpec(
        name="/mcp",
        summary="Inspect configured MCP clients.",
        usage="/mcp [verbose] [--json]",
        payload_shape="table",
        help="Inspect configured MCP clients and discovered tools.",
        example="/mcp verbose",
        empty_state=EmptyState(
            message="No MCP clients are configured.",
            remediation="Add MCP clients to your Craik configuration.",
        ),
    ),
    SlashCommandSpec(
        name="/gateway",
        summary="Inspect gateway state.",
        usage="/gateway",
        payload_shape="tree",
        help="Inspect gateway configs, runtime states, and schedules.",
        empty_state=EmptyState(message="No gateway state found."),
    ),
    SlashCommandSpec(
        name="/exit",
        summary="Exit the shell.",
        usage="/exit",
        payload_shape="markdown",
        help="Exit the interactive shell.",
        aliases=("quit",),
    ),
)


def slash_command_specs() -> list[SlashCommandSpec]:
    """Return registered slash command specs in stable order."""
    return list(SLASH_COMMAND_SPECS)


def slash_command_spec_by_name(name: str) -> SlashCommandSpec | None:
    """Return the command spec for a slash-prefixed or bare command name."""
    normalized = name.strip().removeprefix("/")
    for spec in SLASH_COMMAND_SPECS:
        if spec.command_name == normalized or normalized in spec.aliases:
            return spec
    return None


def slash_command_names(*, include_aliases: bool = True) -> list[str]:
    """Return registered slash command names without slash prefixes."""
    values: list[str] = []
    for spec in SLASH_COMMAND_SPECS:
        values.append(spec.command_name)
        if include_aliases:
            values.extend(spec.aliases)
    return values


def is_known_command_name(name: str) -> bool:
    """Return whether a bare or slash-prefixed name is registered."""
    return slash_command_spec_by_name(name) is not None
