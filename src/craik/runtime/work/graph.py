"""Work graph export for local runtime objects."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from craik.contracts.models import (
    AgentMessage,
    Assumption,
    CapabilityReceipt,
    ContradictionReport,
    EvidenceReference,
    Handoff,
    HumanDelegationPoint,
    IntentLock,
    MemoryProposal,
    TaskRequest,
    TaskRun,
    WorkGraphEdge,
    WorkGraphExport,
    WorkGraphNode,
)
from craik.runtime.policy.redaction import redact
from craik.runtime.store import LocalStore


class WorkGraphError(RuntimeError):
    """Base error for work graph export failures."""


class WorkGraphTaskNotFoundError(WorkGraphError):
    """Raised when a task-scoped export references an unknown task."""


class WorkGraphExporter:
    """Export graph-connected local runtime contracts."""

    def __init__(self, store: LocalStore) -> None:
        self._store = store

    def export(self, *, task_id: str | None = None) -> WorkGraphExport:
        """Build a deterministic graph export."""
        if task_id is not None and self._store.get_task(task_id) is None:
            raise WorkGraphTaskNotFoundError(f"unknown task: {task_id}")

        builder = _GraphBuilder(task_id=task_id)
        tasks = _filter_by_task(self._store.list_tasks(), task_id)
        for task in tasks:
            builder.add_task(task)
        for lock in _filter_by_task(self._store.list_intent_locks(), task_id):
            builder.add_intent_lock(lock)
        for run in _filter_by_task(self._store.list_task_runs(), task_id):
            builder.add_run(run)
        for case_file in _filter_by_task(self._store.list_case_files(), task_id):
            builder.add_node(
                id=f"case:{case_file.id}",
                type="case_file",
                label=case_file.id,
                task_id=case_file.task_id,
                metadata={"objective": case_file.objective},
            )
            builder.add_edge(
                type="has_case_file",
                from_node=f"task:{case_file.task_id}",
                to_node=f"case:{case_file.id}",
            )
            for evidence in case_file.evidence:
                builder.add_evidence(evidence, task_id=case_file.task_id)
                builder.add_edge(
                    type="cites",
                    from_node=f"case:{case_file.id}",
                    to_node=f"evidence:{evidence.id}",
                )
            for assumption in case_file.assumptions:
                builder.add_assumption(assumption)
                builder.add_edge(
                    type="contains_assumption",
                    from_node=f"case:{case_file.id}",
                    to_node=f"assumption:{assumption.id}",
                )
            for contradiction in case_file.contradictions:
                builder.add_contradiction(contradiction, task_id=case_file.task_id)
                builder.add_edge(
                    type="contains_contradiction",
                    from_node=f"case:{case_file.id}",
                    to_node=f"contradiction:{contradiction.id}",
                )
        for receipt in _filter_by_task(self._store.list_receipts(), task_id):
            builder.add_receipt(receipt)
        for message in _filter_by_task(self._store.list_agent_messages(), task_id):
            builder.add_agent_message(message)
        for proposal in _filter_by_task(self._store.list_proposals(), task_id):
            builder.add_proposal(proposal)
        for handoff in _filter_by_task(self._store.list_handoffs(), task_id):
            builder.add_handoff(handoff)
        for delegation in _filter_by_task(self._store.list_human_delegations(), task_id):
            builder.add_human_delegation(delegation)
        for evidence in _filter_by_task(self._store.list_evidence(), task_id):
            builder.add_evidence(evidence, task_id=_task_id_from_evidence(evidence))
        for assumption in _filter_by_task(self._store.list_assumptions(), task_id):
            builder.add_assumption(assumption)
        if task_id is None:
            contradictions = self._store.list_contradictions()
        else:
            contradictions = [
                report for report in self._store.list_contradictions() if report.task_id == task_id
            ]
        for report in contradictions:
            builder.add_contradiction(report, task_id=report.task_id)
            if report.task_id:
                builder.add_edge(
                    type="has_contradiction",
                    from_node=f"task:{report.task_id}",
                    to_node=f"contradiction:{report.id}",
                )
            for evidence_id in report.evidence_ids:
                evidence = self._store.get_evidence(evidence_id)
                if evidence is not None:
                    builder.add_evidence(evidence, task_id=report.task_id)
                builder.add_edge(
                    type="supported_by",
                    from_node=f"contradiction:{report.id}",
                    to_node=f"evidence:{evidence_id}",
                )
        for event in _filter_by_task(self._store.list_graph_events(), task_id):
            builder.add_event_endpoint(event.from_node, task_id=event.task_id)
            builder.add_event_endpoint(event.to_node, task_id=event.task_id)
            builder.add_edge(
                type=event.type,
                from_node=event.from_node,
                to_node=event.to_node,
                metadata=event.metadata,
            )

        export_id = f"graph_{task_id}" if task_id else "graph_all"
        return WorkGraphExport(
            id=export_id,
            task_id=task_id,
            nodes=builder.nodes(),
            edges=builder.edges(),
            created_at=datetime.now(UTC),
        )


class _GraphBuilder:
    def __init__(self, *, task_id: str | None) -> None:
        self._task_id = task_id
        self._nodes: dict[str, WorkGraphNode] = {}
        self._edges: dict[str, WorkGraphEdge] = {}

    def add_task(self, task: TaskRequest) -> None:
        self.add_node(
            id=f"task:{task.id}",
            type="task",
            label=task.title,
            task_id=task.id,
            metadata={
                "mode": task.mode,
                "priority": task.priority,
                "source_handoff_id": task.source_handoff_id,
                "source_task_id": task.source_task_id,
            },
        )
        if task.source_handoff_id:
            self.add_node(
                id=f"handoff:{task.source_handoff_id}",
                type="handoff",
                label=task.source_handoff_id,
                task_id=task.id,
                metadata={
                    "source": "consumed_handoff",
                    "source_task_id": task.source_task_id,
                },
            )
            self.add_edge(
                type="continues_handoff",
                from_node=f"handoff:{task.source_handoff_id}",
                to_node=f"task:{task.id}",
                metadata={"source_task_id": task.source_task_id},
            )

    def add_handoff(self, handoff: Handoff) -> None:
        self.add_node(
            id=f"handoff:{handoff.id}",
            type="handoff",
            label=handoff.summary,
            task_id=handoff.task_id,
            metadata={"status": handoff.status, "agent": handoff.agent},
        )
        self.add_edge(
            type="has_handoff",
            from_node=f"task:{handoff.task_id}",
            to_node=f"handoff:{handoff.id}",
        )
        for receipt_id in handoff.receipt_ids:
            self.add_edge(
                type="records_receipt",
                from_node=f"handoff:{handoff.id}",
                to_node=f"receipt:{receipt_id}",
            )
        for proposal_id in handoff.memory_proposal_ids:
            self.add_edge(
                type="proposes_memory",
                from_node=f"handoff:{handoff.id}",
                to_node=f"proposal:{proposal_id}",
            )

    def add_run(self, run: TaskRun) -> None:
        self.add_node(
            id=f"run:{run.id}",
            type="run",
            label=f"{run.runner_id}: {run.status}",
            task_id=run.task_id,
            metadata={"status": run.status, "phase": run.phase, "role_id": run.role_id},
        )
        self.add_edge(type="has_run", from_node=f"task:{run.task_id}", to_node=f"run:{run.id}")
        if run.intent_lock_id:
            self.add_edge(
                type="depends_on",
                from_node=f"run:{run.id}",
                to_node=f"intent_lock:{run.intent_lock_id}",
            )

    def add_intent_lock(self, lock: IntentLock) -> None:
        self.add_node(
            id=f"intent_lock:{lock.id}",
            type="intent_lock",
            label=lock.accepted_interpretation,
            task_id=lock.task_id,
            metadata={"in_scope": lock.in_scope, "out_of_scope": lock.out_of_scope},
        )
        self.add_edge(
            type="has_intent_lock",
            from_node=f"task:{lock.task_id}",
            to_node=f"intent_lock:{lock.id}",
        )

    def add_human_delegation(self, delegation: HumanDelegationPoint) -> None:
        self.add_node(
            id=f"delegation:{delegation.id}",
            type="delegation",
            label=delegation.summary,
            task_id=delegation.task_id,
            metadata={"kind": delegation.kind, "status": delegation.status},
        )
        self.add_edge(
            type="blocks",
            from_node=f"delegation:{delegation.id}",
            to_node=f"task:{delegation.task_id}",
        )

    def add_receipt(self, receipt: CapabilityReceipt) -> None:
        self.add_node(
            id=f"receipt:{receipt.id}",
            type="receipt",
            label=f"{receipt.capability}: {receipt.result.status}",
            task_id=receipt.task_id,
            metadata={
                "capability": receipt.capability,
                "status": receipt.result.status,
                "target": receipt.target,
            },
        )
        self.add_edge(
            type="has_receipt",
            from_node=f"task:{receipt.task_id}",
            to_node=f"receipt:{receipt.id}",
        )

    def add_agent_message(self, message: AgentMessage) -> None:
        self.add_node(
            id=f"message:{message.id}",
            type="agent_message",
            label=message.subject,
            task_id=message.task_id,
            metadata={
                "kind": message.kind,
                "status": message.status,
                "from_agent": message.from_agent,
                "to_agent": message.to_agent,
                "from_role_kind": message.from_role_kind,
                "to_role_kind": message.to_role_kind,
            },
        )
        self.add_edge(
            type="has_message",
            from_node=f"task:{message.task_id}",
            to_node=f"message:{message.id}",
        )
        if message.run_id:
            self.add_edge(
                type="message_in_run",
                from_node=f"run:{message.run_id}",
                to_node=f"message:{message.id}",
            )
        if message.handoff_id:
            self.add_edge(
                type="message_references_handoff",
                from_node=f"message:{message.id}",
                to_node=f"handoff:{message.handoff_id}",
            )
        for receipt_id in message.receipt_ids:
            self.add_edge(
                type="records_receipt",
                from_node=f"message:{message.id}",
                to_node=f"receipt:{receipt_id}",
            )

    def add_proposal(self, proposal: MemoryProposal) -> None:
        self.add_node(
            id=f"proposal:{proposal.id}",
            type="memory_proposal",
            label=f"{proposal.operation} {proposal.fact.relation}",
            task_id=proposal.task_id,
            metadata={
                "status": proposal.status,
                "entity": proposal.fact.entity,
                "scope": proposal.fact.scope,
            },
        )
        self.add_edge(
            type="has_memory_proposal",
            from_node=f"task:{proposal.task_id}",
            to_node=f"proposal:{proposal.id}",
        )
        fact_node = f"fact:{_slug(proposal.fact.entity)}:{_slug(proposal.fact.relation)}"
        self.add_node(
            id=fact_node,
            type="fact",
            label=proposal.fact.relation,
            task_id=proposal.task_id,
            metadata={
                "entity": proposal.fact.entity,
                "value": proposal.fact.value,
                "source": proposal.fact.source,
                "scope": proposal.fact.scope,
                "trust_class": proposal.fact.trust_class,
            },
        )
        self.add_edge(type="proposes_fact", from_node=f"proposal:{proposal.id}", to_node=fact_node)
        for evidence in proposal.evidence:
            self.add_evidence(evidence, task_id=proposal.task_id)
            self.add_edge(
                type="supported_by",
                from_node=f"proposal:{proposal.id}",
                to_node=f"evidence:{evidence.id}",
            )

    def add_evidence(self, evidence: EvidenceReference, *, task_id: str | None) -> None:
        self.add_node(
            id=f"evidence:{evidence.id}",
            type="evidence",
            label=evidence.summary,
            task_id=task_id,
            metadata={
                "kind": evidence.kind,
                "source": evidence.source,
                "locator": evidence.locator,
            },
        )

    def add_assumption(self, assumption: Assumption) -> None:
        self.add_node(
            id=f"assumption:{assumption.id}",
            type="assumption",
            label=assumption.statement,
            task_id=assumption.task_id,
            metadata={"status": assumption.status, "confidence": assumption.confidence},
        )
        self.add_edge(
            type="has_assumption",
            from_node=f"task:{assumption.task_id}",
            to_node=f"assumption:{assumption.id}",
        )

    def add_contradiction(
        self,
        contradiction: ContradictionReport,
        *,
        task_id: str | None,
    ) -> None:
        self.add_node(
            id=f"contradiction:{contradiction.id}",
            type="contradiction",
            label=contradiction.summary,
            task_id=task_id,
            metadata={"status": contradiction.status, "owner": contradiction.owner},
        )

    def add_event_endpoint(self, node_id: str, *, task_id: str) -> None:
        """Ensure live graph event endpoints are visible in active graph queries."""
        if node_id in self._nodes:
            return
        node_type, _, raw_label = node_id.partition(":")
        self.add_node(
            id=node_id,
            type=node_type or "artifact",
            label=raw_label or node_id,
            task_id=task_id,
            metadata={"source": "work_graph_event"},
        )

    def add_node(
        self,
        *,
        id: str,
        type: str,
        label: str,
        task_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        if self._task_id is not None and task_id not in {None, self._task_id}:
            return
        self._nodes[id] = WorkGraphNode(
            id=str(redact(id).value),
            type=type,
            label=str(redact(label).value),
            task_id=task_id,
            metadata=_redact_metadata(metadata),
        )

    def add_edge(
        self,
        *,
        type: str,
        from_node: str,
        to_node: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if from_node not in self._nodes or to_node not in self._nodes:
            return
        edge_id = f"edge:{type}:{from_node}:{to_node}"
        self._edges[edge_id] = WorkGraphEdge.model_validate(
            {
                "id": str(redact(edge_id).value),
                "type": type,
                "from": str(redact(from_node).value),
                "to": str(redact(to_node).value),
                "metadata": _redact_metadata(metadata or {}),
            }
        )

    def nodes(self) -> list[WorkGraphNode]:
        return [self._nodes[key] for key in sorted(self._nodes)]

    def edges(self) -> list[WorkGraphEdge]:
        return [self._edges[key] for key in sorted(self._edges)]


def _filter_by_task(items: list[Any], task_id: str | None) -> list[Any]:
    if task_id is None:
        return items
    return [
        item
        for item in items
        if getattr(item, "task_id", None) == task_id or getattr(item, "id", None) == task_id
    ]


def _task_id_from_evidence(evidence: EvidenceReference) -> str | None:
    if evidence.id.startswith("evidence_task_"):
        return evidence.id.removeprefix("evidence_").rsplit("_", 1)[0]
    return None


def _redact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            redacted[key] = str(redact(value).value)
        else:
            redacted[key] = value
    return redacted


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "value"
