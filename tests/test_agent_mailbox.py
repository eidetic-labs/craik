from pathlib import Path

import pytest
from pydantic import ValidationError

from craik.contracts.models import AgentMessage, PolicyEnvelope
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore
from craik.runtime.work.coordination.mailbox import (
    AgentMessageAuthorizationError,
    AgentMessageNotFoundError,
    record_agent_message_received,
    send_agent_message,
)
from craik.runtime.work.graph import WorkGraphExporter
from craik.runtime.work.runs import TaskRunManager


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    local_store = LocalStore.from_paths(paths)
    local_store.initialize()
    try:
        yield local_store
    finally:
        local_store.close()


def test_send_agent_message_persists_message_and_receipt(store: LocalStore) -> None:
    _seed_orchestrator_run(store)
    message = send_agent_message(
        store,
        policy=_policy(),
        task_id="task_multi_agent",
        from_agent="agent:orchestrator",
        to_agent="agent:verifier",
        from_role_id="role_orchestrator",
        from_role_kind="orchestrator",
        to_role_id="role_verifier",
        to_role_kind="verifier",
        run_id="run_multi_agent",
        handoff_id="handoff_multi_agent",
        subject="Review implementation",
        body="Please verify the patch before handoff.",
    )
    receipt = store.get_receipt(message.receipt_ids[0])

    assert store.get_agent_message(message.id) == message
    assert receipt is not None
    assert receipt.capability == "agent.message.send"
    assert receipt.result.metadata["message_id"] == message.id
    assert receipt.result.metadata["to_role_kind"] == "verifier"


def test_send_agent_message_rejects_spoofed_sender(store: LocalStore) -> None:
    _seed_orchestrator_run(store)

    with pytest.raises(AgentMessageAuthorizationError, match="not authorized"):
        send_agent_message(
            store,
            policy=_policy(),
            task_id="task_multi_agent",
            from_agent="agent:verifier",
            to_agent="agent:orchestrator",
            from_role_id="role_verifier",
            from_role_kind="verifier",
            run_id="run_multi_agent",
            subject="Spoofed",
            body="This should not be accepted.",
        )


def test_send_agent_message_requires_sender_run(store: LocalStore) -> None:
    with pytest.raises(AgentMessageAuthorizationError, match="require a sender run_id"):
        send_agent_message(
            store,
            policy=_policy(),
            task_id="task_multi_agent",
            from_agent="agent:orchestrator",
            to_agent="agent:verifier",
            subject="Review implementation",
            body="Please verify the patch before handoff.",
        )


def test_send_agent_message_preserves_same_subject_history(store: LocalStore) -> None:
    _seed_orchestrator_run(store)
    first = send_agent_message(
        store,
        policy=_policy(),
        task_id="task_multi_agent",
        from_agent="agent:orchestrator",
        to_agent="agent:verifier",
        from_role_id="role_orchestrator",
        from_role_kind="orchestrator",
        run_id="run_multi_agent",
        subject="Review implementation",
        body="First body.",
    )
    second = send_agent_message(
        store,
        policy=_policy(),
        task_id="task_multi_agent",
        from_agent="agent:orchestrator",
        to_agent="agent:verifier",
        from_role_id="role_orchestrator",
        from_role_kind="orchestrator",
        run_id="run_multi_agent",
        subject="Review implementation",
        body="Second body.",
    )

    assert first.id != second.id
    assert store.get_agent_message(first.id).body == "First body."
    assert store.get_agent_message(second.id).body == "Second body."


def test_receive_agent_message_appends_receipt(store: LocalStore) -> None:
    _seed_orchestrator_run(store)
    message = send_agent_message(
        store,
        policy=_policy(),
        task_id="task_multi_agent",
        from_agent="agent:orchestrator",
        to_agent="agent:verifier",
        from_role_id="role_orchestrator",
        from_role_kind="orchestrator",
        run_id="run_multi_agent",
        subject="Review implementation",
        body="Please verify the patch before handoff.",
    )

    received = record_agent_message_received(
        store,
        policy=_policy(),
        message_id=message.id,
        received_by="agent:verifier",
    )

    assert received.status == "received"
    assert received.received_at is not None
    assert len(received.receipt_ids) == 2
    assert store.get_receipt(received.receipt_ids[1]) is not None


def test_receive_agent_message_rejects_missing_message(store: LocalStore) -> None:
    with pytest.raises(AgentMessageNotFoundError, match="unknown agent message"):
        record_agent_message_received(
            store,
            policy=_policy(),
            message_id="agent_message_missing",
            received_by="agent:verifier",
        )


def test_agent_message_contract_rejects_missing_receipts() -> None:
    with pytest.raises(ValidationError, match="receipt_ids"):
        AgentMessage(
            id="agent_message_invalid",
            task_id="task_multi_agent",
            from_agent="agent:a",
            to_agent="agent:b",
            subject="Invalid",
            body="Missing receipt provenance.",
            receipt_ids=[],
            created_at="2026-05-20T12:00:00Z",
        )


def test_work_graph_exports_agent_message_receipt_edges(store: LocalStore) -> None:
    _seed_orchestrator_run(store)
    message = send_agent_message(
        store,
        policy=_policy(),
        task_id="task_multi_agent",
        from_agent="agent:orchestrator",
        to_agent="agent:verifier",
        from_role_id="role_orchestrator",
        from_role_kind="orchestrator",
        run_id="run_multi_agent",
        subject="Review implementation",
        body="Please verify the patch before handoff.",
    )

    export = WorkGraphExporter(store).export()

    node_ids = {node.id for node in export.nodes}
    edge_types = {(edge.type, edge.from_node, edge.to_node) for edge in export.edges}
    assert f"message:{message.id}" in node_ids
    assert (
        "records_receipt",
        f"message:{message.id}",
        f"receipt:{message.receipt_ids[0]}",
    ) in edge_types


def _policy() -> PolicyEnvelope:
    return PolicyEnvelope(
        id="policy_task_multi_agent",
        task_id="task_multi_agent",
        actor="agent:orchestrator",
        profile="strict",
        allowed_capabilities=["repo.read", "memory.read", "receipt.write"],
        denied_capabilities=["repo.write", "memory.write"],
    )


def _seed_orchestrator_run(store: LocalStore) -> None:
    TaskRunManager(store).create(
        task_id="task_multi_agent",
        case_file_id="case_multi_agent",
        policy_envelope_id="policy_task_multi_agent",
        runner_id="provider_openai_chat",
        runner_mode="fixture",
        run_id="run_multi_agent",
        role_id="role_orchestrator",
        role_kind="orchestrator",
    )
