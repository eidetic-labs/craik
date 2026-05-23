import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import AgentSessionEvent
from craik.runtime.agents.session_portability import (
    export_agent_session,
    import_session_export,
)
from craik.runtime.agents.sessions import start_agent_session
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_export_agent_session_redacts_events_and_preserves_provenance(tmp_path) -> None:
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    now = datetime(2026, 5, 23, 6, 10, tzinfo=UTC)
    try:
        session = start_agent_session(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
            endpoint_url="http://127.0.0.1:8766",
            now=now,
        )
        event = AgentSessionEvent(
            id="event_1",
            session_id=session.id,
            event_type="prompt",
            operator_subject="operator-123",
            provider_id="provider_openai",
            metadata={"content": "Bearer secretfixture12345", "token": "raw"},
            created_at=now,
        )
        export = export_agent_session(session, [event], now=now)
        payload = export.model_dump(mode="json", by_alias=True)

        assert payload["schema"] == "craik.session_export"
        assert export.provenance.source_session_id == "agent_session_docs"
        assert export.session.endpoint_url is None
        assert export.events[0].metadata["content"] == "Bearer [REDACTED]"
        assert export.events[0].metadata["token"] == "[REDACTED]"
        assert "secretfixture" not in json.dumps(payload)
    finally:
        store.close()


def test_import_adjacent_transcript_marks_imported_and_blocks_tool_authority(
    tmp_path,
) -> None:
    path = tmp_path / "transcript.json"
    path.write_text(
        json.dumps(
            {
                "id": "session-ext-1",
                "title": "External transcript",
                "provider": "external",
                "model": "model-a",
                "messages": [
                    {"role": "user", "content": "hello token=rawsecret"},
                    {
                        "role": "assistant",
                        "content": "done",
                        "tool_calls": [{"name": "shell", "args": {"cmd": "rm -rf /tmp/x"}}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    imported = import_session_export(path, now=datetime(2026, 5, 23, 6, 20, tzinfo=UTC))
    payload = imported.model_dump(mode="json")

    assert imported.session.id == "imported_session_ext_1"
    assert imported.session.status == "stopped"
    assert imported.session.recovery_metadata["imported"] is True
    assert imported.provenance.source_session_id == "session-ext-1"
    assert imported.unsupported_fields[0].path == "$.messages[1].tool_calls"
    assert imported.events[1].metadata["unsupported_tool_call_count"] == 1
    assert "rm -rf" not in json.dumps(payload)
    assert "rawsecret" not in json.dumps(payload)


def test_import_craik_export_preserves_original_identity_as_metadata(tmp_path) -> None:
    now = datetime(2026, 5, 23, 6, 30, tzinfo=UTC)
    store = LocalStore(tmp_path / "craik.sqlite3")
    store.initialize()
    try:
        session = start_agent_session(
            store,
            session_id="agent_session_docs",
            operator_subject="operator-123",
            provider_id="provider_openai",
            now=now,
        )
        export_path = tmp_path / "session.json"
        export_path.write_text(
            export_agent_session(session, [], now=now).model_dump_json(by_alias=True),
            encoding="utf-8",
        )
    finally:
        store.close()

    imported = import_session_export(export_path, now=now)

    assert imported.session.id == "imported_agent_session_docs"
    assert imported.session.recovery_metadata["source_session_id"] == "agent_session_docs"
    assert imported.provenance.imported is True


def test_session_import_portable_cli(tmp_path) -> None:
    path = tmp_path / "transcript.json"
    path.write_text(
        json.dumps(
            {"conversation_id": "conv-1", "transcript": [{"speaker": "user", "text": "hi"}]}
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["session", "import-portable", "--path", str(path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session"]["recovery_metadata"]["imported"] is True
    assert payload["provenance"]["source_session_id"] == "conv-1"
