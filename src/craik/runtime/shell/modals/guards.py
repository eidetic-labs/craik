"""Reusable checks for interactive prompt modal metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping

from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.modals import (
    ModalClass,
    canonical_modal_registry,
    modal_supports_secret_capture,
    resolve_modal_class,
)

SENSITIVE_PROMPT_RE = re.compile(
    r"(api[_-]?key|credential|password|secret|token)",
    re.IGNORECASE,
)


def modal_mapping_failures(
    registry: AutoSlashRegistry,
    *,
    modal_registry: Mapping[str, ModalClass] | None = None,
) -> list[str]:
    """Return failures for unresolved interactive prompt modal targets."""
    available_modals = modal_registry or canonical_modal_registry()
    failures: list[str] = []
    for entry in registry.inventory:
        metadata = entry.metadata
        if metadata is None:
            continue
        for prompt_name, modal_name in sorted(metadata.interactive_prompts.items()):
            if not prompt_name.strip():
                failures.append(f"{entry.command_name}: interactive prompt name is blank")
            if not modal_name.strip():
                failures.append(
                    f"{entry.command_name}: {prompt_name!r} modal target is blank"
                )
                continue
            if resolve_modal_class(modal_name, available_modals) is None:
                failures.append(
                    f"{entry.command_name}: {prompt_name!r} references unknown modal "
                    f"{modal_name!r}"
                )
    return failures


def modal_security_failures(
    registry: AutoSlashRegistry,
    *,
    modal_registry: Mapping[str, ModalClass] | None = None,
) -> list[str]:
    """Return failures for sensitive prompt mappings without masked input support."""
    available_modals = modal_registry or canonical_modal_registry()
    failures: list[str] = []
    for entry in registry.inventory:
        metadata = entry.metadata
        if metadata is None:
            continue
        for prompt_name, modal_name in sorted(metadata.interactive_prompts.items()):
            if not SENSITIVE_PROMPT_RE.search(f"{prompt_name} {modal_name}"):
                continue
            modal_class = resolve_modal_class(modal_name, available_modals)
            if modal_class is None:
                continue
            if not modal_supports_secret_capture(modal_class):
                failures.append(
                    f"{entry.command_name}: sensitive prompt {prompt_name!r} maps to "
                    f"{modal_name!r}, which does not support masked input"
                )
    return failures
