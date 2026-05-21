"""Markdown rendering for handoff records."""

from __future__ import annotations

from craik.contracts.models import Handoff, SelfAudit


def render_markdown(handoff: Handoff) -> str:
    """Render a deterministic Markdown handoff."""
    sections = [
        f"# Handoff: {handoff.task_id}",
        "",
        f"- Status: {handoff.status}",
        f"- Agent: {handoff.agent}",
        f"- Project: {handoff.project_id}",
        f"- Intent lock: {handoff.intent_lock_id or 'none'}",
        f"- Auth profile: {handoff.auth_profile_id or 'none'}",
        f"- Operator: {_operator_label(handoff)}",
        "",
        "## Summary",
        "",
        handoff.summary,
        "",
        "## Self-Audit",
        "",
        *_checklist(handoff.self_audit),
        "",
        "## Completed Actions",
        "",
        *_bullets(handoff.completed_actions),
        "",
        "## Validation",
        "",
        *_bullets(handoff.tests_run),
        "",
        "## Receipts",
        "",
        *_bullets(handoff.receipt_ids),
        "",
        "## Assumptions",
        "",
        *_bullets(handoff.assumptions),
        "",
        "## Context Debt",
        "",
        *_bullets(handoff.context_debt),
        "",
        "## Policy Exceptions",
        "",
        *_bullets(handoff.policy_exceptions),
        "",
        "## Memory Proposals",
        "",
        *_bullets(handoff.memory_proposal_ids),
        "",
        "## Runner Metadata",
        "",
        *_runner_metadata_bullets(handoff.runner_metadata),
        "",
        "## Next Steps",
        "",
        *_bullets(handoff.next_steps),
        "",
    ]
    return "\n".join(sections)


def _operator_label(handoff: Handoff) -> str:
    if handoff.operator_subject is None:
        return "none"
    if handoff.operator_issuer:
        return f"{handoff.operator_issuer}#{handoff.operator_subject}"
    return handoff.operator_subject


def _runner_metadata_bullets(metadata: list[dict[str, object]]) -> list[str]:
    if not metadata:
        return ["- none"]
    bullets: list[str] = []
    for item in metadata:
        runner_id = item.get("runner_id", "unknown")
        adapter = item.get("adapter", "unknown")
        version = item.get("adapter_version", "unknown")
        mode = item.get("execution_mode", "unknown")
        trust = item.get("trust_profile", {})
        trust_level = trust.get("level", "unknown") if isinstance(trust, dict) else "unknown"
        bullets.append(
            f"- {runner_id}: adapter={adapter}; version={version}; mode={mode}; trust={trust_level}"
        )
    return bullets


def _checklist(audit: SelfAudit) -> list[str]:
    return [
        f"- [{'x' if audit.schema_validated else ' '}] Schema validated",
        f"- [{'x' if audit.redaction_reviewed else ' '}] Redaction reviewed",
        f"- [{'x' if audit.receipts_reviewed else ' '}] Receipts reviewed",
        f"- [{'x' if audit.assumptions_reviewed else ' '}] Assumptions reviewed",
        f"- [{'x' if audit.validation_recorded else ' '}] Validation recorded",
        (
            f"- [{'x' if audit.policy_exceptions_disclosed else ' '}] "
            "Policy exceptions disclosed"
        ),
        *_bullets(audit.notes),
    ]


def _bullets(values: list[str]) -> list[str]:
    if not values:
        return ["- None"]
    return [f"- {value}" for value in values]
