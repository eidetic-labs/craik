"""Structured provider command implementations."""

from __future__ import annotations

from typing import Any

from craik.runtime.contract import CommandResult, NextAction
from craik.runtime.local_models import (
    check_local_model_health,
    list_local_model_presets,
    provider_for_local_model_preset,
)
from craik.runtime.providers.model_providers import (
    ModelProviderNotFoundError,
    default_model_provider_registry,
    provider_selection_payload,
)
from craik.runtime.providers.provider_certification import (
    ProviderCertificationMatrix,
    provider_certification_matrix,
)


def provider_summary_payload() -> list[dict[str, Any]]:
    """Return redacted registered provider rows."""
    registry = default_model_provider_registry()
    return [provider.model_dump(mode="json", by_alias=True) for provider in registry.list()]


def provider_list_result() -> CommandResult:
    """Return registered providers as a structured command result."""
    return CommandResult(
        payload=provider_summary_payload(),
        shape="card_list",
        next_actions=[
            NextAction(
                text="run /provider login <provider>",
                command="/provider login",
                field="provider",
            )
        ],
    )


def provider_show_result(provider_id: str) -> CommandResult:
    """Return one registered provider as a structured command result."""
    registry = default_model_provider_registry()
    try:
        provider = registry.require(provider_id)
    except ModelProviderNotFoundError as error:
        raise ValueError(str(error)) from None
    return CommandResult(payload=provider.model_dump(mode="json", by_alias=True), shape="card")


def provider_select_result(
    provider_id: str,
    *,
    mode: str = "chat",
    policy_envelope_id: str | None = None,
    receipt_ids: list[str] | None = None,
) -> CommandResult:
    """Return a redacted provider selection payload."""
    registry = default_model_provider_registry()
    try:
        provider = registry.require(provider_id)
        payload = provider_selection_payload(
            provider,
            mode=mode,
            policy_envelope_id=policy_envelope_id,
            receipt_ids=receipt_ids,
        )
    except (ModelProviderNotFoundError, ValueError) as error:
        raise ValueError(str(error)) from None
    return CommandResult(payload=payload, shape="card")


def provider_certification_result(provider_id: str | None = None) -> CommandResult:
    """Return provider certification matrix data."""
    matrix = provider_certification_matrix()
    if provider_id is not None:
        rows = [row for row in matrix.rows if row.provider_id == provider_id]
        if not rows:
            raise ValueError(f"unknown provider certification row: {provider_id}")
        matrix = ProviderCertificationMatrix(generated_at=matrix.generated_at, rows=rows)
    return CommandResult(payload=matrix.model_dump(mode="json", by_alias=True), shape="card")


def provider_local_presets_result() -> CommandResult:
    """Return local provider routing presets."""
    payload = [
        {
            **preset.model_dump(mode="json", by_alias=True),
            "provider": provider_for_local_model_preset(preset.id).model_dump(
                mode="json",
                by_alias=True,
            ),
        }
        for preset in list_local_model_presets()
    ]
    return CommandResult(payload=payload, shape="card_list")


def provider_local_health_result(
    preset_id: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = 2.0,
) -> CommandResult:
    """Return local endpoint health data without loading provider credentials."""
    try:
        health = check_local_model_health(
            preset_id,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as error:
        raise ValueError(str(error)) from None
    return CommandResult(payload=health.model_dump(mode="json"), shape="card")
