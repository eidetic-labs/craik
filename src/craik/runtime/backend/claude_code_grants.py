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


def _put_claude_code_grants(store: LocalStore, task_id: str) -> list[str]:
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
            id=f"grant_{task_id.removeprefix('task_')}_claude_receipt_write",
            task_id=task_id,
            capability="receipt.write",
            target=CapabilityTarget(paths=["craik-runtime"]),
            operations=["write"],
            reason="Allow Craik to persist receipts for the delegated model run.",
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


CLAUDE_CODE_RUN_APPROVED_ENV = "CRAIK_CLAUDE_CODE_RUN_APPROVED"


def _require_claude_code_run_approval(env: dict[str, str] | None) -> None:
    values = env or {}
    if values.get(CLAUDE_CODE_RUN_APPROVED_ENV) == "1":
        return
    raise ValueError(
        "Audited run requires operator approval for repo.write.docs, "
        "receipt.write, and shell.test. Use the TUI or set "
        f"`{CLAUDE_CODE_RUN_APPROVED_ENV}=1` for a deliberate non-interactive run."
    )


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
                    "capabilities": [
                        "repo.read",
                        "repo.write.docs",
                        "receipt.write",
                        "shell.test",
                    ],
                },
            ),
            created_at=datetime.now(UTC),
        )
    )
