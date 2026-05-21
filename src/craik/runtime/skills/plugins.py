"""Runtime capture points for governed plugin contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from craik.contracts.models import (
    PluginCapabilityGrant,
    PluginDescriptor,
    PluginProbation,
    PluginProbationCriterion,
    PluginProbationDecision,
    PluginReceipt,
    ReceiptResult,
)
from craik.runtime.policy.redaction import redact
from craik.runtime.store import LocalStore


def install_plugin_descriptor(store: LocalStore, manifest_path: Path) -> PluginDescriptor:
    """Load and persist a plugin descriptor contract from a JSON manifest."""
    descriptor = PluginDescriptor.model_validate(_load_json(manifest_path))
    store.put_plugin_descriptor(descriptor)
    return descriptor


def record_plugin_probation(store: LocalStore, probation: PluginProbation) -> PluginProbation:
    """Persist a plugin probation record with store-level integrity."""
    store.put_plugin_probation(probation)
    stored = store.get_plugin_probation(probation.id)
    if stored is None:
        raise RuntimeError("stored plugin probation could not be reloaded")
    return stored


def review_plugin_probation(
    store: LocalStore,
    probation_id: str,
    *,
    decision: str,
    decided_by: str,
    rationale: str,
    evidence_ids: list[str],
    compatibility_check_ids: list[str] | None = None,
) -> PluginProbation:
    """Promote, reject, or expire a probationary plugin after operator review."""
    probation = store.get_plugin_probation(probation_id)
    if probation is None:
        raise ValueError(f"unknown plugin probation: {probation_id}")
    now = datetime.now(UTC)
    decision_kind = {"pass": "promote", "fail": "reject"}.get(decision, decision)
    criteria = [
        criterion.model_copy(update={"passed": True, "evidence_ids": evidence_ids})
        if decision_kind == "promote"
        else criterion
        for criterion in probation.criteria
    ]
    updated = probation.model_copy(
        update={
            "status": "promoted" if decision_kind == "promote" else "rejected",
            "criteria": criteria,
            "compatibility_check_ids": compatibility_check_ids
            or probation.compatibility_check_ids
            or evidence_ids,
            "evidence_ids": sorted(set([*probation.evidence_ids, *evidence_ids])),
            "decision": PluginProbationDecision(
                decision=decision_kind,  # type: ignore[arg-type]
                decided_by=decided_by,
                rationale=rationale,
                evidence_ids=evidence_ids,
                decided_at=now,
            ),
            "durable_trust_granted": decision_kind == "promote",
        }
    )
    return record_plugin_probation(store, updated)


def record_plugin_capability_grant(
    store: LocalStore,
    grant: PluginCapabilityGrant,
) -> PluginCapabilityGrant:
    """Persist a plugin capability grant."""
    store.put_plugin_capability_grant(grant)
    return grant


def record_plugin_receipt(
    store: LocalStore,
    *,
    receipt_id: str,
    task_id: str,
    actor: str,
    plugin_descriptor_id: str,
    action: str,
    capability_grant_ids: list[str],
    trust_boundary: str,
    status: str,
    summary: str,
    metadata: dict[str, Any] | None,
    evidence_ids: list[str],
    handoff_ids: list[str],
    plugin_probation_id: str | None = None,
    created_at: datetime | None = None,
) -> PluginReceipt:
    """Build, redact, and persist a plugin receipt."""
    safe_summary = str(redact(summary).value)
    safe_metadata = redact(metadata or {}).value
    if not isinstance(safe_metadata, dict):
        safe_metadata = {"value": safe_metadata}
    safe_metadata["redacted"] = True
    receipt = PluginReceipt(
        id=receipt_id,
        task_id=task_id,
        actor=actor,
        plugin_descriptor_id=plugin_descriptor_id,
        plugin_probation_id=plugin_probation_id,
        action=action,
        capability_grant_ids=capability_grant_ids,
        trust_boundary=trust_boundary,  # type: ignore[arg-type]
        result=ReceiptResult(
            status=status,  # type: ignore[arg-type]
            summary=safe_summary,
            metadata=safe_metadata,
        ),
        evidence_ids=evidence_ids,
        handoff_ids=handoff_ids,
        redacted=True,
        created_at=created_at or datetime.now(UTC),
    )
    store.put_plugin_receipt(receipt)
    stored = store.get_plugin_receipt(receipt.id)
    if stored is None:
        raise RuntimeError("stored plugin receipt could not be reloaded")
    return stored


def probation_from_descriptor(
    *,
    probation_id: str,
    descriptor: PluginDescriptor,
    policy_envelope_id: str,
    evidence_ids: list[str],
    created_at: datetime | None = None,
) -> PluginProbation:
    """Create a default probation record for an installed descriptor."""
    return PluginProbation(
        id=probation_id,
        plugin_descriptor_id=descriptor.id,
        policy_envelope_id=policy_envelope_id,
        criteria=[
            PluginProbationCriterion(
                name="compatibility",
                passed=False,
                summary="Compatibility must be reviewed before durable trust.",
            )
        ],
        evidence_ids=evidence_ids,
        created_at=created_at or datetime.now(UTC),
    )


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
