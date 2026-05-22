import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.channels.webhook_ingress import (
    persist_webhook_ingress_receipt,
    validate_webhook_request,
    webhook_signature,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

NOW = datetime(2026, 5, 22, 12, 30, tzinfo=UTC)
runner = CliRunner()


def test_successful_webhook_ingress_persists_receipt_readable_by_cli(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    _put_operator_session(home)
    body = json.dumps(
        {
            "event_id": "evt_v011_001",
            "event_type": "channel.message",
            "timestamp": NOW.isoformat(),
            "payload": {"text": "secret body is redacted"},
        },
        sort_keys=True,
    ).encode("utf-8")
    result = validate_webhook_request(
        body=body,
        headers={"X-Craik-Signature": webhook_signature(body, "secret")},
        secret="secret",
        allowed_event_types={"channel.message"},
        seen_event_ids=set(),
        now=NOW,
    )
    assert result.accepted is True

    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        receipt = persist_webhook_ingress_receipt(
            store,
            result=result,
            task_id="task_webhook_v011",
            actor="gateway:webhook",
            policy_profile="strict",
            policy_envelope_id="policy_gateway",
            created_at=NOW,
        )
        assert store.get_gateway_receipt(receipt.id) is not None
    finally:
        store.close()

    shown = runner.invoke(
        app,
        ["receipts", "show", receipt.id],
        env={"CRAIK_HOME": str(home)},
    )

    assert shown.exit_code == 0, shown.output
    payload = json.loads(shown.stdout)
    assert payload["id"] == receipt.id
    assert payload["result"]["metadata"]["ingress_status"] == "accepted"
    assert "secret body is redacted" not in shown.stdout


def _put_operator_session(home: Path) -> None:
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator:test",
            email="operator@example.test",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
