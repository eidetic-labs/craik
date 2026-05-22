import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from craik.contracts.models import ChannelAllowlist, GatewaySchedule, ScheduledAutomation
from craik.runtime.channels.allowlist import evaluate_channel_allowlist
from craik.runtime.channels.identity import pair_channel_identity, unpaired_channel_identity
from craik.runtime.channels.messaging import (
    default_messaging_channel_contract,
    inbound_message_receipt,
    normalize_inbound_message,
)
from craik.runtime.channels.persistence import persist_gateway_channel_artifacts
from craik.runtime.channels.policy import select_channel_policy
from craik.runtime.channels.scheduled_automations import (
    run_scheduled_automation_tick,
    scheduled_automation_receipt,
)
from craik.runtime.channels.webhook_ingress import (
    JsonFileWebhookReplayStore,
    validate_webhook_request,
    webhook_ingress_receipt,
    webhook_signature,
)
from craik.runtime.gateway import default_gateway_config, run_gateway_daemon
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

NOW = datetime(2026, 5, 22, 4, 45, tzinfo=UTC)


class _FakeGatewayServer:
    server_address = ("127.0.0.1", 8765)

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        return

    def shutdown(self) -> None:
        return

    def server_close(self) -> None:
        return


def test_v0_8_gateway_pipeline_persists_ingress_policy_receipts_and_schedule(
    tmp_path: Path,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        config = default_gateway_config(
            project_id="project_gateway",
            policy_envelope_id="policy_gateway_admin",
            created_at=NOW,
        ).model_copy(update={"enabled": True})
        store.put_gateway_config(config)

        stop_event = threading.Event()
        stop_event.set()
        stopped = run_gateway_daemon(
            paths,
            stop_event=stop_event,
            server_factory=lambda config: _FakeGatewayServer(),
        )
        assert stopped.status == "stopped"
        assert store.get_gateway_runtime_state(stopped.id) == stopped

        adapter = default_messaging_channel_contract(created_at=NOW)
        unpaired = unpaired_channel_identity(
            pairing_id="pairing_alice",
            channel="messaging",
            external_id="alice_ext",
            service="fixture-chat",
            display_name="Alice",
            created_at=NOW,
        )
        pairing = pair_channel_identity(
            unpaired,
            subject="operator:alice",
            policy_envelope_id="policy_channel_alice",
            paired_by="operator:admin",
            audit_id="receipt_pairing_alice",
            paired_at=NOW + timedelta(minutes=1),
        )
        allowlist = ChannelAllowlist.model_validate(
            {
                "id": "allowlist_messaging_gateway",
                "channel": "messaging",
                "rules": [
                    {
                        "id": "allow_alice",
                        "description": "Allow paired fixture sender Alice.",
                        "channel": "messaging",
                        "service": "fixture-chat",
                        "sender_external_ids": ["alice_ext"],
                    }
                ],
                "created_at": NOW,
                "updated_at": NOW,
            }
        )
        persist_gateway_channel_artifacts(
            store,
            adapter_contract=adapter,
            identity_pairing=pairing,
            allowlist=allowlist,
        )

        body = json.dumps(
            {
                "event_id": "webhook_evt_001",
                "event_type": "channel.message",
                "timestamp": NOW.isoformat(),
                "payload": {"sender_id": "alice_ext", "text": "please run status"},
            },
            sort_keys=True,
        ).encode("utf-8")
        replay_store = JsonFileWebhookReplayStore(paths.state / "webhook_seen.json")
        webhook_result = validate_webhook_request(
            body=body,
            headers={"X-Craik-Signature": webhook_signature(body, "fixture-secret")},
            secret="fixture-secret",
            allowed_event_types={"channel.message"},
            seen_event_ids=set(),
            replay_store=replay_store,
            now=NOW,
        )
        assert webhook_result.accepted is True
        webhook_receipt = store.put_gateway_receipt(
            webhook_ingress_receipt(
                result=webhook_result,
                task_id="task_gateway_ingress",
                actor="gateway:webhook",
                policy_profile="strict",
                policy_envelope_id="policy_gateway_admin",
                created_at=NOW,
            )
        )
        duplicate = validate_webhook_request(
            body=body,
            headers={"X-Craik-Signature": webhook_signature(body, "fixture-secret")},
            secret="fixture-secret",
            allowed_event_types={"channel.message"},
            seen_event_ids=set(),
            replay_store=replay_store,
            now=NOW,
        )
        assert duplicate.status == "duplicate"

        event = normalize_inbound_message(
            event_id=webhook_result.event_id or "missing",
            sender_id="alice_ext",
            text="please run status",
            received_at=NOW,
            thread_id="thread_gateway",
            identity_id=pairing.id,
            policy_envelope_id=pairing.policy_envelope_id,
            metadata={"service": "fixture-chat"},
        )
        allowlist_decision = evaluate_channel_allowlist(allowlist, event)
        assert allowlist_decision.allowed is True
        selection = select_channel_policy(
            event=event,
            pairing=pairing,
            allowlist_decision=allowlist_decision,
            policy_id="policy_channel_alice",
            task_id="task_gateway_ingress",
            allowed_capabilities=[
                "channel.message.receive",
                "channel.message.respond",
                "gateway.schedule.execute",
                "receipt.write",
            ],
        )
        assert selection.allowed is True
        assert selection.policy is not None
        message_receipt = store.put_gateway_receipt(
            inbound_message_receipt(
                event=event,
                task_id="task_gateway_ingress",
                actor=selection.subject or "operator:alice",
                policy_profile=selection.policy.profile,
                policy_envelope_id=selection.policy.id,
                created_at=NOW,
            )
        )
        persist_gateway_channel_artifacts(store, policy=selection.policy)

        schedule = GatewaySchedule(
            id="schedule_gateway_status",
            project_id="project_gateway",
            title="Gateway status",
            objective="Summarize gateway health.",
            cron="0 9 * * *",
            policy_envelope_id=selection.policy.id,
            channel="scheduler",
            receipt_ids=[webhook_receipt.id, message_receipt.id],
        )
        automation = ScheduledAutomation(
            id="automation_gateway_status",
            schedule=schedule,
            enabled=True,
            policy_envelope_id=selection.policy.id,
            receipt_ids=[message_receipt.id],
        )
        automation_result = run_scheduled_automation_tick(
            automation=automation,
            policy=selection.policy,
            tick_id="2026-05-22T09:00:00Z",
            run_at=NOW,
            seen_tick_ids=set(),
        )
        assert automation_result.status == "created"
        assert automation_result.task_creation is not None
        assert automation_result.task_creation.task is not None
        store.put_task(automation_result.task_creation.task)
        automation_receipt = store.put_gateway_receipt(
            scheduled_automation_receipt(
                result=automation_result,
                policy=selection.policy,
                created_at=NOW,
            )
        )
        persist_gateway_channel_artifacts(
            store,
            schedule=schedule,
            automation=automation,
            receipt=automation_receipt,
        )

        assert store.get_channel_adapter_contract(adapter.id) == adapter
        assert store.get_channel_identity_pairing(pairing.id) == pairing
        assert store.get_channel_allowlist(allowlist.id) == allowlist
        assert store.get_channel_policy_envelope(selection.policy.id) == selection.policy
        assert store.get_gateway_schedule(schedule.id) == schedule
        assert store.get_scheduled_automation(automation.id) == automation
        assert store.get_task(automation_result.task_creation.task.id) is not None
        assert {receipt.id for receipt in store.list_gateway_receipts()} >= {
            webhook_receipt.id,
            message_receipt.id,
            automation_receipt.id,
        }
    finally:
        store.close()
