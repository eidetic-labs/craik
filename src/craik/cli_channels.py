"""Channel adapter CLI commands."""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Annotated, cast

import typer

from craik.cli_operator_auth import operator_identity_or_fail
from craik.runtime.channels.persistence import persist_gateway_channel_artifacts
from craik.runtime.channels.real_adapters import (
    RealChannelService,
    channel_outbound_response,
    channel_setup_plan,
    diagnose_channel_adapter,
    normalize_real_channel_inbound,
    outbound_delivery_receipt,
    real_channel_adapter_contract,
    supported_real_channel_services,
)
from craik.runtime.channels.setup_artifacts import channel_setup_artifacts
from craik.runtime.store import LocalStore

channels_app = typer.Typer(help="Configure and inspect real channel adapters.")


class ChannelService(str, Enum):
    """CLI values for supported real channel adapters."""

    webchat = "webchat"
    telegram = "telegram"
    discord = "discord"
    slack = "slack"


@channels_app.command("list")
def channel_list_command() -> None:
    """List supported real channel adapters."""
    payload = [
        real_channel_adapter_contract(service).model_dump(mode="json", by_alias=True)
        for service in supported_real_channel_services()
    ]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@channels_app.command("setup")
def channel_setup_command(service: ChannelService) -> None:
    """Persist channel adapter setup artifacts and show a redacted setup plan."""
    operator_subject = operator_identity_or_fail()
    channel_service = _service_value(service)
    plan = channel_setup_plan(channel_service, env=dict(os.environ))
    adapter, pairing, allowlist, policy = channel_setup_artifacts(
        channel_service,
        operator_subject=operator_subject,
    )
    store = LocalStore.from_env()
    try:
        store.initialize()
        persist_gateway_channel_artifacts(
            store,
            adapter_contract=adapter,
            identity_pairing=pairing,
            allowlist=allowlist,
            policy=policy,
        )
    finally:
        store.close()
    payload = plan.as_dict()
    payload["persisted"] = {
        "adapter_contract_id": adapter.id,
        "identity_pairing_id": pairing.id,
        "allowlist_id": allowlist.id,
        "policy_envelope_id": policy.id,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@channels_app.command("doctor")
def channel_doctor_command(service: ChannelService) -> None:
    """Show redacted channel adapter diagnostics."""
    operator_identity_or_fail()
    channel_service = _service_value(service)
    diagnostic = diagnose_channel_adapter(channel_service, env=dict(os.environ))
    store = LocalStore.from_env()
    try:
        store.initialize()
        persisted = {
            "adapter_contract": store.get_channel_adapter_contract(
                f"channel_adapter_{channel_service}"
            )
            is not None,
            "identity_pairing": store.get_channel_identity_pairing(
                f"channel_pairing_{channel_service}"
            )
            is not None,
            "allowlist": store.get_channel_allowlist(f"allowlist_{channel_service}") is not None,
            "policy_envelope": store.get_channel_policy_envelope(
                f"policy_channel_{channel_service}"
            )
            is not None,
        }
    finally:
        store.close()
    payload = diagnostic.as_dict()
    payload["persisted"] = persisted
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@channels_app.command("normalize-fixture")
def channel_normalize_fixture_command(
    service: ChannelService,
    raw_json: Annotated[
        str,
        typer.Argument(
            help="Provider event JSON object. Run `craik channels fixture-schema SERVICE` first."
        ),
    ],
) -> None:
    """Normalize a provider event fixture without contacting the provider."""
    raw = json.loads(raw_json)
    if not isinstance(raw, dict):
        raise typer.BadParameter("raw_json must be a JSON object")
    event = normalize_real_channel_inbound(_service_value(service), raw)
    typer.echo(json.dumps(event, indent=2, sort_keys=True))


@channels_app.command("fixture-schema")
def channel_fixture_schema_command(service: ChannelService) -> None:
    """Print the expected inbound fixture JSON shape for a channel service."""
    typer.echo(json.dumps(_fixture_schema(_service_value(service)), indent=2, sort_keys=True))


@channels_app.command("respond-fixture")
def channel_respond_fixture_command(
    service: ChannelService,
    event_id: str,
    response_id: str,
    summary: str,
    delivered: Annotated[bool, typer.Option("--delivered/--failed")] = True,
) -> None:
    """Build a redacted outbound response fixture and delivery receipt."""
    response = channel_outbound_response(
        _service_value(service),
        response_id=response_id,
        event_id=event_id,
        summary=summary,
    )
    receipt = outbound_delivery_receipt(
        _service_value(service),
        response=response,
        task_id="task_channel_fixture",
        actor=f"adapter:{service.value}",
        policy_profile="strict",
        policy_envelope_id=f"policy_channel_{service.value}",
        delivered=delivered,
        error=None if delivered else "fixture delivery failure",
    )
    payload = {
        "response": response,
        "receipt": receipt.model_dump(mode="json", by_alias=True),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _service_value(service: ChannelService) -> RealChannelService:
    return cast(RealChannelService, service.value)


def _fixture_schema(service: RealChannelService) -> dict[str, object]:
    examples: dict[RealChannelService, dict[str, object]] = {
        "webchat": {
            "required": ["message_id", "user_id", "text"],
            "optional": ["session_id", "origin"],
            "example": {
                "message_id": "m1",
                "user_id": "u1",
                "text": "hello",
                "session_id": "browser-session",
                "origin": "localhost",
            },
        },
        "telegram": {
            "required": ["update_id", "message.message_id", "message.from.id", "message.text"],
            "optional": ["message.chat.id", "message.chat.type"],
            "example": {
                "update_id": 10,
                "message": {
                    "message_id": 10,
                    "from": {"id": 42},
                    "chat": {"id": 42, "type": "private"},
                    "text": "hello",
                },
            },
        },
        "discord": {
            "required": ["id", "content", "author.id"],
            "optional": ["channel_id", "guild_id"],
            "example": {
                "id": "msg1",
                "content": "hello",
                "author": {"id": "user1"},
                "channel_id": "channel1",
                "guild_id": "guild1",
            },
        },
        "slack": {
            "required": ["event.user", "event.text"],
            "optional": ["event_id", "event.client_msg_id", "event.ts", "event.channel", "team_id"],
            "example": {
                "team_id": "T1",
                "event_id": "Ev123",
                "event": {
                    "user": "U1",
                    "text": "hello",
                    "channel": "C1",
                    "client_msg_id": "m1",
                },
            },
        },
    }
    return {"service": service, "schema": examples[service]}
