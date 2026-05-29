"""Argument parsing helpers for model slash commands."""

from __future__ import annotations

from craik.runtime.model_commands import parse_model_options

_MODEL_SET_FLAGS = {
    "--display-name",
    "--backend",
    "--reasoning-effort",
    "--service-tier",
    "--temperature",
    "--max-output-tokens",
    "--option",
}


def parse_model_set_args(args: tuple[str, ...]) -> tuple[str, str | None, str, dict[str, object]]:
    selector = args[0]
    display_name: str | None = None
    backend = "provider"
    reasoning_effort: str | None = None
    service_tier: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    passthrough: list[str] = []
    index = 1
    while index < len(args):
        flag = args[index]
        if flag not in _MODEL_SET_FLAGS:
            raise ValueError(f"unsupported /model set option: {flag}")
        if index + 1 >= len(args):
            raise ValueError(f"{flag} requires a value")
        value = args[index + 1]
        if flag == "--display-name":
            display_name = value
        elif flag == "--backend":
            backend = value
        elif flag == "--reasoning-effort":
            reasoning_effort = value
        elif flag == "--service-tier":
            service_tier = value
        elif flag == "--temperature":
            temperature = float(value)
        elif flag == "--max-output-tokens":
            max_output_tokens = int(value)
        elif flag == "--option":
            passthrough.append(value)
        index += 2
    options = parse_model_options(
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        passthrough=passthrough,
    )
    return selector, display_name, backend, options
