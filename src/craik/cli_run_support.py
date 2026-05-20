"""Support helpers for run CLI commands."""

from __future__ import annotations

from typing import Any, cast

import typer

from craik.contracts.models import AgentRoleKind, CapabilityGrant, CapabilityTarget
from craik.runtime.providers.provider_runner import ProviderBackedRunResult


def fixture_shell_grant(task_id: str) -> CapabilityGrant:
    """Return the deterministic shell grant used by fixture provider runs."""
    return CapabilityGrant(
        id=f"grant_{task_id.removeprefix('task_')}_fixture_shell",
        task_id=task_id,
        capability="shell.execute",
        target=CapabilityTarget(paths=["fixture-action"]),
        operations=["execute"],
        reason="Allow the deterministic MVP fixture action.",
        approved_by="user:local-operator",
    )


def role_kind(value: str) -> AgentRoleKind:
    """Validate a CLI role kind option."""
    allowed = {
        "orchestrator",
        "implementer",
        "verifier",
        "adversarial_reviewer",
        "policy_reviewer",
        "docs_reviewer",
        "memory_curator",
        "adjudicator",
    }
    if value not in allowed:
        raise typer.BadParameter(f"unsupported role kind: {value}")
    return cast(AgentRoleKind, value)


def provider_run_payload(result: ProviderBackedRunResult) -> dict[str, Any]:
    """Return the JSON payload for provider-backed run execution."""
    provider_results = [
        provider_result.model_dump(mode="json", by_alias=True)
        for provider_result in result.provider_results
    ]
    receipt_ids = sorted(
        {
            receipt_id
            for output in (result.loop.output_captures if result.loop else [])
            for receipt_id in output.output.receipt_ids
        }
        | set(result.run.receipt_ids)
    )
    return {
        "schema": "craik.provider_backed_run_execution",
        "version": "0.1.0",
        "status": result.run.status,
        "run": result.run.model_dump(mode="json", by_alias=True),
        "handoff": result.handoff.model_dump(mode="json", by_alias=True),
        "compiled_prompt": result.compiled_prompt.model_dump(mode="json", by_alias=True),
        "provider_results": provider_results,
        "provider_ids": sorted(
            {provider_result["provider_id"] for provider_result in provider_results}
        ),
        "provider_families": sorted(
            {provider_result["provider_family"] for provider_result in provider_results}
        ),
        "receipt_ids": receipt_ids,
        "interrupted_error": result.interrupted_error,
        "next_commands": [
            f"craik run inspect {result.run.id} --include-outputs",
            f"craik handoff show {result.handoff.id}",
            f"craik receipts list --task-id {result.run.task_id}",
        ],
    }
