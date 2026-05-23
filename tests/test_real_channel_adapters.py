import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.channels.allowlist import evaluate_channel_allowlist
from craik.runtime.channels.identity import pair_channel_identity, unpaired_channel_identity
from craik.runtime.channels.policy import select_channel_policy
from craik.runtime.channels.real_adapters import (
    MESSAGE_RESPOND_CAPABILITY,
    channel_outbound_response,
    channel_setup_plan,
    default_channel_allowlist,
    diagnose_channel_adapter,
    normalize_real_channel_inbound,
    outbound_delivery_receipt,
    real_channel_adapter_contract,
    supported_real_channel_services,
)
from craik.runtime.paths import ensure_craik_home

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
runner = CliRunner()


def test_real_channel_contracts_cover_first_adapter_batch() -> None:
    contracts = [
        real_channel_adapter_contract(service, created_at=NOW)
        for service in supported_real_channel_services()
    ]

    assert [contract.identity.service for contract in contracts] == [
        "webchat",
        "telegram",
        "discord",
        "slack",
    ]
    for contract in contracts:
        assert contract.identity.channel == "messaging"
        assert contract.trust_boundary.allowlist_required is True
        assert contract.trust_boundary.inbound_identity_required is True
        assert contract.trust_boundary.secrets_in_config_allowed is False
        assert contract.receipts.required is True


def test_channel_setup_plan_uses_secret_reference_without_token_material() -> None:
    plan = channel_setup_plan("telegram", env={"CRAIK_TELEGRAM_BOT_TOKEN": "secret-token"})

    payload = plan.as_dict()

    assert payload["service"] == "telegram"
    assert payload["secret_ref"] == {"env_var": "CRAIK_TELEGRAM_BOT_TOKEN"}
    assert "secret-token" not in str(payload)
    assert payload["pairing_required"] is True
    assert payload["diagnostics"]["token_resolved"] is True


def test_real_channel_inbound_normalizes_provider_specific_identity() -> None:
    event = normalize_real_channel_inbound(
        "slack",
        {
            "event_id": "Ev123",
            "team_id": "T1",
            "event": {"user": "U1", "channel": "C1", "text": "run status"},
        },
        received_at=NOW,
        identity_id="channel_identity_slack_u1",
        policy_envelope_id="policy_channel_slack",
    )

    assert event["event_id"] == "slack_Ev123"
    assert event["channel"] == "messaging"
    assert event["sender"]["external_id"] == "slack:U1"
    assert event["sender"]["identity_id"] == "channel_identity_slack_u1"
    assert event["sender"]["policy_envelope_id"] == "policy_channel_slack"
    assert event["text"] == "run status"
    assert event["thread_id"] == "C1"
    assert event["metadata"]["service"] == "slack"
    assert event["metadata"]["workspace"] == "T1"


def test_allowlist_and_pairing_gate_unknown_channel_sender() -> None:
    allowlist = default_channel_allowlist(
        "discord",
        sender_external_ids=["discord:alice"],
        workspace_ids=["guild-1"],
        created_at=NOW,
    )
    event = normalize_real_channel_inbound(
        "discord",
        {
            "id": "msg-1",
            "author": {"id": "bob"},
            "content": "deploy",
            "channel_id": "chan-1",
            "guild_id": "guild-1",
        },
        received_at=NOW,
    )

    decision = evaluate_channel_allowlist(allowlist, event)

    assert decision.allowed is False
    assert decision.sender_external_id == "discord:bob"


def test_channel_policy_selects_paired_and_allowlisted_sender() -> None:
    allowlist = default_channel_allowlist(
        "webchat",
        sender_external_ids=["webchat:user-1"],
        workspace_ids=["local-browser"],
        created_at=NOW,
    )
    event = normalize_real_channel_inbound(
        "webchat",
        {"message_id": "m1", "user_id": "user-1", "text": "status", "origin": "local-browser"},
        received_at=NOW,
    )
    decision = evaluate_channel_allowlist(allowlist, event)
    pairing = pair_channel_identity(
        unpaired_channel_identity(
            pairing_id="channel_identity_webchat_user_1",
            channel="messaging",
            external_id="webchat:user-1",
            service="webchat",
            created_at=NOW,
        ),
        subject="operator:alice",
        policy_envelope_id="policy_channel_webchat",
        paired_by="operator:alice",
        audit_id="receipt_pair_webchat_user_1",
        paired_at=NOW,
    )

    selection = select_channel_policy(
        event=event,
        pairing=pairing,
        allowlist_decision=decision,
        policy_id="policy_channel_webchat_m1",
        task_id="task_channel",
    )

    assert selection.allowed is True
    assert selection.policy is not None
    assert MESSAGE_RESPOND_CAPABILITY in selection.policy.approval_required


def test_outbound_delivery_failure_is_receipted_and_redacted() -> None:
    response = channel_outbound_response(
        "telegram",
        response_id="response-1",
        event_id="telegram_10",
        summary="Could not deliver",
        text="secret text",
    )

    receipt = outbound_delivery_receipt(
        "telegram",
        response=response,
        task_id="task_channel",
        actor="adapter:telegram",
        policy_profile="strict",
        policy_envelope_id="policy_channel_telegram",
        delivered=False,
        error="provider rejected request",
        created_at=NOW,
    )

    assert receipt.capability == MESSAGE_RESPOND_CAPABILITY
    assert receipt.result.status == "failed"
    assert receipt.result.metadata["delivery_error"] == "provider rejected request"
    assert "secret text" not in str(receipt.model_dump(mode="json"))
    assert receipt.redacted is True


def test_channel_doctor_reports_missing_token_without_leaking_values() -> None:
    diagnostic = diagnose_channel_adapter("slack", env={}).as_dict()

    assert diagnostic["configured"] is False
    assert diagnostic["token_resolved"] is False
    assert "CRAIK_SLACK_BOT_TOKEN" in diagnostic["warnings"][0]


def test_channels_cli_exposes_setup_and_fixture_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)
    setup = runner.invoke(
        app,
        ["channels", "setup", "webchat"],
        env={"CRAIK_HOME": str(home), "CRAIK_WEBCHAT_TOKEN": "super-secret-value"},
    )
    assert setup.exit_code == 0
    assert "CRAIK_WEBCHAT_TOKEN" in setup.stdout
    assert "super-secret-value" not in setup.stdout

    normalized = runner.invoke(
        app,
        [
            "channels",
            "normalize-fixture",
            "webchat",
            '{"message_id":"m1","user_id":"u1","text":"hello"}',
        ],
    )
    assert normalized.exit_code == 0
    assert "webchat:u1" in normalized.stdout

    schema = runner.invoke(app, ["channels", "fixture-schema", "webchat"])
    assert schema.exit_code == 0
    payload = json.loads(schema.stdout)
    assert payload["service"] == "webchat"
    assert "message_id" in payload["schema"]["required"]


def _put_operator_session(home: Path) -> None:
    ensure_craik_home({"CRAIK_HOME": str(home)})
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
