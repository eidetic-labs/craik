"""Schema metadata for Craik slash commands."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from craik.runtime.contract.command_result import PayloadShape as PayloadShape

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
    slash: str | None = Field(default=None, alias="/")
    F: str | None = None
    escape: str | None = None


class ThemeArgs(BaseModel):
    """Validated arguments for /theme."""

    model_config = ConfigDict(frozen=True)

    theme: Literal["dark", "light", "monochrome"] | None = None


class ModelArgs(BaseModel):
    """Validated arguments for /model."""

    model_config = ConfigDict(frozen=True)

    action: Literal["list", "set"] | None = None
    selector: str | None = None

    @model_validator(mode="after")
    def _selector_required_for_set(self) -> ModelArgs:
        if self.action == "set" and not self.selector:
            raise ValueError("model set requires a provider/model selector")
        if self.action != "set" and self.selector:
            raise ValueError("model selector is only valid with `set`")
        if self.selector and (
            "/" not in self.selector
            or self.selector.startswith("/")
            or self.selector.endswith("/")
        ):
            raise ValueError("model set requires a provider/model selector")
        return self


class NamedArg(BaseModel):
    """Validated single non-empty argument."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)


class SlashCommandSpec(BaseModel):
    """Durable command metadata shared by slash rendering, help, and CI."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

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
    args_schema: type[BaseModel] | None = None
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
