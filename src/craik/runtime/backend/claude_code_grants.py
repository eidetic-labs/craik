"""Claude Code grant and approval receipt helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from craik.contracts.models import (
    CapabilityGrant,
    CapabilityReceipt,
    CapabilityTarget,
    ReceiptResult,
)
from craik.runtime.store import LocalStore


def _put_craik_internal_grants(store: LocalStore, task_id: str) -> list[str]:
    """Provision Craik's own infrastructure capability grants.

    These are not agent capabilities the operator governs; they are how Craik
    fulfills its purpose (persisting its audit record). They are always granted
    under Craik's own system authority and are never withheld by any
    operator-approval path. ``receipt.write`` is recorded metadata for audit
    attribution only — ``store.put_receipt`` writes unconditionally and never
    enforces this grant at runtime.
    """
    grants = [
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_receipt_write",
            task_id=task_id,
            capability="receipt.write",
            target=CapabilityTarget(paths=["craik-runtime"]),
            operations=["write"],
            reason=(
                "Craik's own infrastructure authority to persist the audit "
                "receipt for the delegated model run. Always granted under "
                "system:craik authority; never operator-gated."
            ),
            approved_by="system:craik",
        ),
    ]
    for grant in grants:
        store.put_capability_grant(grant)
    return [grant.id for grant in grants]


def _put_claude_code_agent_grants(store: LocalStore, task_id: str) -> list[str]:
    """Provision the agent capabilities the operator governs."""
    grants = [
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_repo_read",
            task_id=task_id,
            capability="repo.read",
            target=CapabilityTarget(paths=["."]),
            operations=["read"],
            reason="Allow Claude Code to inspect the current repository for the audited run.",
            approved_by="user:tui",
        ),
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_repo_write_docs",
            task_id=task_id,
            capability="repo.write.docs",
            target=CapabilityTarget(paths=["docs", "README.md", "CHANGELOG.md"]),
            operations=["read", "write"],
            reason="Allow Claude Code to update documentation for the audited run.",
            approved_by="user:tui",
        ),
        CapabilityGrant(
            id=f"grant_{task_id.removeprefix('task_')}_claude_shell_verify",
            task_id=task_id,
            capability="shell.test",
            target=CapabilityTarget(paths=["."]),
            operations=["execute"],
            reason="Allow Claude Code to run verification commands for documentation changes.",
            approved_by="user:tui",
        ),
    ]
    for grant in grants:
        store.put_capability_grant(grant)
    return [grant.id for grant in grants]


def _put_claude_code_grants(store: LocalStore, task_id: str) -> list[str]:
    """Provision both Craik-internal system grants and operator-governed agent grants.

    Thin compatibility shim that preserves the combined contract for existing
    callers. Craik-internal grants are provisioned unconditionally under system
    authority; agent grants remain operator-attributed.
    """
    internal_ids = _put_craik_internal_grants(store, task_id)
    agent_ids = _put_claude_code_agent_grants(store, task_id)
    return internal_ids + agent_ids


CLAUDE_CODE_RUN_APPROVED_ENV = "CRAIK_CLAUDE_CODE_RUN_APPROVED"


def _run_operator_approved(env: dict[str, str] | None) -> bool:
    """Return whether a REAL operator approval occurred for this run.

    The only honest signal of an operator decision on the delegate-observe path
    is the approval flag, which the TUI sets on modal confirm. No flag means no
    operator decided -- the run still proceeds (delegate-observed), it is just
    not attributed to the operator.
    """
    return (env or {}).get(CLAUDE_CODE_RUN_APPROVED_ENV) == "1"


def _put_claude_code_approval_receipt(
    store: LocalStore,
    task_id: str,
    grant_ids: list[str],
    *,
    operator_approved: bool = True,
) -> CapabilityReceipt:
    actor = "user:tui" if operator_approved else "system:craik"
    capability = "approval.decide" if operator_approved else "authority.delegate"
    reason = (
        "Operator approved Claude Code repository, receipt, and verification grants."
        if operator_approved
        else "Craik selected Claude Code as the default attested backend for Anthropic marker auth."
    )
    summary = (
        "Operator approved audited run authority for this task."
        if operator_approved
        else "Craik delegated the task to Claude Code to capture stream provenance."
    )
    return store.put_receipt(
        CapabilityReceipt(
            id=f"receipt_{task_id.removeprefix('task_')}_claude_code_approval",
            task_id=task_id,
            actor=actor,
            capability=capability,
            target="claude-code-run-grants",
            policy_profile="trusted-local",
            reason=reason,
            result=ReceiptResult(
                status="passed",
                summary=summary,
                metadata={
                    "backend": "claude-code",
                    "approved": operator_approved,
                    "default_attested_backend": not operator_approved,
                    "grant_ids": grant_ids,
                    # Operator-approved agent capabilities only. receipt.write is
                    # Craik's own system authority (system:craik) and is not
                    # attributed to operator approval here.
                    "capabilities": [
                        "repo.read",
                        "repo.write.docs",
                        "shell.test",
                    ],
                },
            ),
            created_at=datetime.now(UTC),
        )
    )
