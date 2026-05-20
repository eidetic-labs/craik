import json
from pathlib import Path
from typing import Any

import pytest

from craik.contracts.models import (
    Assumption,
    CapabilityReceipt,
    CaseFile,
    EvidenceReference,
    Handoff,
    MemoryProposal,
    TaskRequest,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore
from craik.runtime.work.graph import WorkGraphExporter, WorkGraphTaskNotFoundError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "contracts" / "v0_1" / "contracts.json"


@pytest.fixture(scope="module")
def fixtures() -> dict[str, dict[str, Any]]:
    return json.loads(FIXTURE_PATH.read_text())


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    local_store = LocalStore.from_paths(paths)
    local_store.initialize()
    try:
        yield local_store
    finally:
        local_store.close()


def test_work_graph_export_links_task_runtime_objects(
    store: LocalStore,
    fixtures: dict[str, dict[str, Any]],
) -> None:
    _load_graph_fixture(store, fixtures)

    export = WorkGraphExporter(store).export(task_id="task_docs_reconcile")

    node_ids = [node.id for node in export.nodes]
    edge_types = {(edge.type, edge.from_node, edge.to_node) for edge in export.edges}
    assert export.id == "graph_task_docs_reconcile"
    assert node_ids == sorted(node_ids)
    assert "task:task_docs_reconcile" in node_ids
    assert "handoff:handoff_docs_reconcile" in node_ids
    assert "receipt:receipt_pytest" in node_ids
    assert "proposal:memprop_contract_surface" in node_ids
    assert "evidence:evidence_readme_status" in node_ids
    assert "assumption:assumption_demo_docs_stale" in node_ids
    assert (
        "has_handoff",
        "task:task_docs_reconcile",
        "handoff:handoff_docs_reconcile",
    ) in edge_types
    assert (
        "records_receipt",
        "handoff:handoff_docs_reconcile",
        "receipt:receipt_pytest",
    ) in edge_types
    assert (
        "supported_by",
        "proposal:memprop_contract_surface",
        "evidence:evidence_readme_status",
    ) in edge_types


def test_work_graph_export_is_deterministic(
    store: LocalStore,
    fixtures: dict[str, dict[str, Any]],
) -> None:
    _load_graph_fixture(store, fixtures)

    first = WorkGraphExporter(store).export(task_id="task_docs_reconcile")
    second = WorkGraphExporter(store).export(task_id="task_docs_reconcile")

    assert _stable(first) == _stable(second)


def test_work_graph_export_links_consumed_handoff_to_follow_up_task(
    store: LocalStore,
    fixtures: dict[str, dict[str, Any]],
) -> None:
    source_handoff = Handoff.model_validate(fixtures["craik.handoff"])
    follow_up_payload = dict(fixtures["craik.task_request"])
    follow_up_payload.update(
        {
            "id": "task_follow_up",
            "title": "Follow up from handoff",
            "source_handoff_id": source_handoff.id,
            "source_task_id": source_handoff.task_id,
            "source_run_id": "run_docs_reconcile",
        }
    )
    follow_up_task = TaskRequest.model_validate(follow_up_payload)
    store.put_handoff(source_handoff)
    store.put_task(follow_up_task)

    export = WorkGraphExporter(store).export()

    edge_types = {(edge.type, edge.from_node, edge.to_node) for edge in export.edges}
    follow_up_node = next(node for node in export.nodes if node.id == "task:task_follow_up")
    assert follow_up_node.metadata["source_handoff_id"] == source_handoff.id
    assert (
        "continues_handoff",
        f"handoff:{source_handoff.id}",
        "task:task_follow_up",
    ) in edge_types


def test_work_graph_export_rejects_unknown_task(store: LocalStore) -> None:
    with pytest.raises(WorkGraphTaskNotFoundError, match="unknown task"):
        WorkGraphExporter(store).export(task_id="task_missing")


def _load_graph_fixture(store: LocalStore, fixtures: dict[str, dict[str, Any]]) -> None:
    task = TaskRequest.model_validate(fixtures["craik.task_request"])
    handoff = Handoff.model_validate(fixtures["craik.handoff"])
    receipt = CapabilityReceipt.model_validate(fixtures["craik.capability_receipt"])
    proposal_payload = dict(fixtures["craik.memory_proposal"])
    proposal_payload["evidence"] = [fixtures["craik.evidence_reference"]]
    proposal = MemoryProposal.model_validate(proposal_payload)
    evidence = EvidenceReference.model_validate(fixtures["craik.evidence_reference"])
    assumption = Assumption.model_validate(fixtures["craik.assumption"])
    case_file = CaseFile.model_validate(fixtures["craik.case_file"])

    store.put_task(task)
    store.put_handoff(handoff)
    store.put_receipt(receipt)
    store.put_proposal(proposal)
    store.put_evidence(evidence)
    store.put_assumption(assumption)
    store.put_case_file(case_file)


def _stable(export):
    payload = export.model_dump(mode="json", by_alias=True)
    payload["created_at"] = "<timestamp>"
    return payload
