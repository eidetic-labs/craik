"""Channel adapter CLI commands."""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Annotated, cast

import typer

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
    """Show a redacted setup plan for a channel adapter."""
    plan = channel_setup_plan(_service_value(service), env=dict(os.environ))
    typer.echo(json.dumps(plan.as_dict(), indent=2, sort_keys=True))


@channels_app.command("doctor")
def channel_doctor_command(service: ChannelService) -> None:
    """Show redacted channel adapter diagnostics."""
    diagnostic = diagnose_channel_adapter(_service_value(service), env=dict(os.environ))
    typer.echo(json.dumps(diagnostic.as_dict(), indent=2, sort_keys=True))


@channels_app.command("normalize-fixture")
def channel_normalize_fixture_command(
    service: ChannelService,
    raw_json: Annotated[str, typer.Argument(help="Provider event JSON object.")],
) -> None:
    """Normalize a provider event fixture without contacting the provider."""
    raw = json.loads(raw_json)
    if not isinstance(raw, dict):
        raise typer.BadParameter("raw_json must be a JSON object")
    event = normalize_real_channel_inbound(_service_value(service), raw)
    typer.echo(json.dumps(event, indent=2, sort_keys=True))


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
