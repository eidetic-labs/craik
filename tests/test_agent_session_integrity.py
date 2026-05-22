from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from craik.contracts.models import AgentSessionEvent
from craik.runtime.agents.sessions import start_agent_session
from craik.runtime.store import CONTRACT_KINDS, LocalStore, LocalStoreCorruptError


def test_agent_session_state_hmac_verified_on_write(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()

    try:
        state = start_agent_session(
            store,
            session_id="agent_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
            now=datetime(2026, 5, 22, 7, 0, tzinfo=UTC),
        )

        stored = store.get_agent_session_state(state.id)
        read_result = store.get_agent_session_state_with_verification(state.id)

        assert stored is not None
        assert stored.receipt_hmac
        assert stored.model_copy(update={"receipt_hmac": None}) == state
        assert read_result is not None
        assert read_result.hmac_status == "verified"
    finally:
        store.close()


def test_agent_session_state_tamper_rejected_by_default_read(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()

    try:
        state = start_agent_session(
            store,
            session_id="agent_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
        )
        _mutate_payload(
            store,
            "craik.agent_session_state",
            state.id,
            lambda payload: payload.update({"provider_id": "provider_tampered"}),
        )

        with pytest.raises(LocalStoreCorruptError, match="agent session state"):
            store.get_agent_session_state(state.id)
        with pytest.raises(LocalStoreCorruptError, match="agent session state"):
            store.list_agent_session_states()
        read_result = store.get_agent_session_state_with_verification(state.id)

        assert read_result is not None
        assert read_result.hmac_status == "tampered"
        assert read_result.state.provider_id == "provider_tampered"
    finally:
        store.close()


def test_agent_session_state_legacy_unsigned_rows_remain_readable(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()

    try:
        state = start_agent_session(
            store,
            session_id="agent_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
        )
        _mutate_payload(
            store,
            "craik.agent_session_state",
            state.id,
            lambda payload: payload.update({"receipt_hmac": None}),
        )

        stored = store.get_agent_session_state(state.id)
        read_result = store.get_agent_session_state_with_verification(state.id)

        assert stored is not None
        assert stored.receipt_hmac is None
        assert read_result is not None
        assert read_result.hmac_status == "unverified"
    finally:
        store.close()


def test_agent_session_event_hmac_verified_and_tamper_detected(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    event = AgentSessionEvent(
        id="agent_event_docs",
        session_id="agent_docs",
        event_type="prompt_received",
        operator_subject="operator-123",
        provider_id="provider_openai",
        created_at=datetime(2026, 5, 22, 7, 5, tzinfo=UTC),
    )

    try:
        store.put_agent_session_event(event)

        stored = store.get_agent_session_event(event.id)
        read_result = store.get_agent_session_event_with_verification(event.id)
        assert stored is not None
        assert stored.receipt_hmac
        assert stored.model_copy(update={"receipt_hmac": None}) == event
        assert read_result is not None
        assert read_result.hmac_status == "verified"

        _mutate_payload(
            store,
            "craik.agent_session_event",
            event.id,
            lambda payload: payload.update({"event_type": "tampered"}),
        )

        with pytest.raises(LocalStoreCorruptError, match="agent session event"):
            store.get_agent_session_event(event.id)
        tampered = store.get_agent_session_event_with_verification(event.id)
        assert tampered is not None
        assert tampered.hmac_status == "tampered"
    finally:
        store.close()


def _mutate_payload(
    store: LocalStore,
    schema_name: str,
    contract_id: str,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    kind = CONTRACT_KINDS[schema_name]
    row = store._connection.execute(
        "SELECT payload_json FROM records WHERE kind = ? AND id = ?",
        (kind, contract_id),
    ).fetchone()
    assert row is not None
    payload = json.loads(str(row["payload_json"]))
    mutate(payload)
    store._connection.execute(
        "UPDATE records SET payload_json = ? WHERE kind = ? AND id = ?",
        (json.dumps(payload, sort_keys=True, separators=(",", ":")), kind, contract_id),
    )
    store._connection.commit()
