"""Adapter dispatch: ``select_adapter`` resolves an id to an adapter instance.

``select_adapter`` accepts exactly the six canonical ``"<vendor>-<surface>"``
ids plus ``"auto"``. The legacy ``BackendPreference`` values (``"provider"`` /
``"claude-code"``) are NOT handled here -- translating those is Task 2.4's job
in ``execute_prompt``.
"""

from __future__ import annotations

from craik.runtime.backend.adapters.anthropic_api import AnthropicAPI
from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.base import Adapter
from craik.runtime.backend.adapters.google_api import GoogleAPI
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.openai_api import OpenAIAPI
from craik.runtime.backend.adapters.openai_cli import OpenAICLI
from craik.runtime.backend.claude_code import anthropic_uses_claude_cli_marker

# Canonical "<vendor>-<surface>" id -> concrete adapter class. The keys here are
# the complete set of valid non-"auto" identifiers.
_REGISTRY: dict[str, type[Adapter]] = {
    "anthropic-cli": AnthropicCLI,
    "anthropic-api": AnthropicAPI,
    "openai-cli": OpenAICLI,
    "openai-api": OpenAIAPI,
    "google-cli": GoogleCLI,
    "google-api": GoogleAPI,
}


def select_adapter(
    identifier: str,
    env: dict[str, str] | None,
    *,
    prompt_source: str = "tui",
) -> Adapter:
    """Resolve ``identifier`` to a concrete adapter instance.

    ``"auto"`` resolves via the existing anthropic-marker rule: ``"anthropic-cli"``
    when ``anthropic_uses_claude_cli_marker(env)`` is True, else ``"anthropic-api"``.
    Any other value must be a canonical ``"<vendor>-<surface>"`` id; ``vendors``
    and ``surfaces`` contain no ``-``, so a valid id splits on ``-`` into exactly
    two parts. Anything else raises ``ValueError``.

    The resolved adapter is constructed with the ORIGINAL ``env`` (possibly
    ``None``) as its ``original_env`` and the operator ``prompt_source`` so the
    live typed ``run()`` (Task 5.7 cutover) threads them to the audited cores
    exactly as the legacy path did. Every concrete adapter accepts both keyword
    arguments (the API adapters record ``prompt_source`` on the created task; the
    CLI adapters thread ``original_env`` to their core).
    """
    if identifier == "auto":
        identifier = "anthropic-cli" if anthropic_uses_claude_cli_marker(env) else "anthropic-api"

    # Parse: a canonical id is exactly two "-"-separated parts.
    parts = identifier.split("-")
    if len(parts) != 2 or identifier not in _REGISTRY:
        valid = ", ".join(sorted([*_REGISTRY, "auto"]))
        raise ValueError(f"unknown adapter identifier {identifier!r}; valid ids are: {valid}")

    return _construct(_REGISTRY[identifier], env, prompt_source)


def _construct(
    adapter_cls: type[Adapter],
    env: dict[str, str] | None,
    prompt_source: str,
) -> Adapter:
    """Build ``adapter_cls`` with ``original_env`` + (for API surfaces) ``prompt_source``.

    The API adapters take a ``prompt_source`` keyword (recorded on the task); the
    CLI adapters do not. The surface is a class attribute, so branch on it rather
    than introspecting the signature.
    """
    if getattr(adapter_cls, "surface", None) == "api":
        return adapter_cls(original_env=env, prompt_source=prompt_source)  # type: ignore[call-arg]
    return adapter_cls(original_env=env)  # type: ignore[call-arg]
