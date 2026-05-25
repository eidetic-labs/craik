"""CommandResult helpers for memory CLI/TUI projections."""

from __future__ import annotations

from craik.contracts.models import MemoryScope, ProposalOperation, TrustClass
from craik.runtime.contract import CommandResult
from craik.runtime.memory.memory import (
    EvidenceRequiredError,
    LocalMemoryStore,
    MemoryProposalNotFoundError,
    build_memory_diff,
    create_proposal,
    evidence_reference,
    preview_memory_impact,
)
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.store import LocalStore


def memory_overview_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return memory proposals, diffs, and impact previews."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        proposals = store.list_proposals()
        diffs = store.list_memory_diffs()
        previews = store.list_memory_impact_previews()
    finally:
        store.close()
    return CommandResult(
        payload={
            "proposals": [_payload(item) for item in proposals],
            "diffs": [_payload(item) for item in diffs],
            "impact_previews": [_payload(item) for item in previews],
        },
        shape="card_list",
        empty_state_message="No memory proposals found.",
    )


def memory_propose_result(
    *,
    task_id: str,
    entity: str,
    relation: str,
    value: str,
    source: str,
    evidence_source: str,
    evidence_locator: str,
    evidence_summary: str,
    confidence: float,
    scope: MemoryScope,
    trust_class: TrustClass,
    operation: ProposalOperation,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Create a reviewable local memory proposal."""
    evidence = evidence_reference(
        task_id=task_id,
        source=evidence_source,
        locator=evidence_locator,
        summary=evidence_summary,
    )
    proposal = create_proposal(
        task_id=task_id,
        entity=entity,
        relation=relation,
        value=value,
        source=source,
        confidence=confidence,
        scope=scope,
        trust_class=trust_class,
        operation=operation,
        evidence=[evidence],
    )
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        proposal = LocalMemoryStore(store).propose(proposal)
    finally:
        store.close()
    return CommandResult(payload=_payload(proposal), shape="card")


def memory_list_result(
    *,
    task_id: str | None = None,
    status: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return local memory proposals."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        proposals = LocalMemoryStore(store).list_proposals(task_id=task_id, status=status)
    finally:
        store.close()
    return CommandResult(payload=[_payload(item) for item in proposals], shape="card_list")


def memory_show_result(proposal_id: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return one local memory proposal."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        proposal = LocalMemoryStore(store).get_proposal(proposal_id)
    finally:
        store.close()
    if proposal is None:
        raise ValueError(f"unknown memory proposal: {proposal_id}")
    return CommandResult(payload=_payload(proposal), shape="card")


def memory_decide_result(
    proposal_id: str,
    *,
    decision: str,
    decided_by: str,
    reason: str,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Approve or reject a local memory proposal."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        memory = LocalMemoryStore(store)
        if decision == "approve":
            proposal = memory.approve(proposal_id, decided_by=decided_by, reason=reason)
        else:
            proposal = memory.reject(proposal_id, decided_by=decided_by, reason=reason)
    except (MemoryProposalNotFoundError, EvidenceRequiredError) as error:
        raise ValueError(str(error)) from None
    finally:
        store.close()
    return CommandResult(payload=_payload(proposal), shape="card")


def memory_search_result(query: str, env: dict[str, str] | None = None) -> CommandResult:
    """Search approved local memory facts."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        facts = LocalMemoryStore(store).search(query)
    finally:
        store.close()
    return CommandResult(payload=[_payload(item) for item in facts], shape="card_list")


def memory_diff_result(task_id: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return and persist a run-scoped memory diff."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        proposals = store.list_proposals()
        diff = build_memory_diff(task_id=task_id, proposals=proposals)
        store.put_memory_diff(diff)
    finally:
        store.close()
    return CommandResult(payload=_payload(diff), shape="card")


def memory_preview_result(task_id: str, env: dict[str, str] | None = None) -> CommandResult:
    """Return and persist a local memory impact preview."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        proposals = store.list_proposals()
        existing_facts = LocalMemoryStore(store).search("")
        preview = preview_memory_impact(
            task_id=task_id,
            proposals=proposals,
            existing_facts=existing_facts,
        )
        store.put_memory_impact_preview(preview)
    finally:
        store.close()
    return CommandResult(payload=_payload(preview), shape="card")


def _payload(model: object) -> dict[str, object]:
    return model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined,no-any-return]
