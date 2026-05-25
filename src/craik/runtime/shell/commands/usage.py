"""Shared cost and quota command results."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from craik.contracts.models import CapabilityReceipt
from craik.runtime.contract import CommandResult, NextAction
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.store import LocalStore, LocalStoreError


def cost_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return provider token usage and explicit cost-accounting gaps."""
    receipts, store_error = _receipts(env)
    usage = _aggregate_usage(receipts)
    latest = _latest_provider_receipt(receipts)
    payload: dict[str, object] = {
        "tokens_in": usage["input"],
        "tokens_out": usage["output"],
        "tokens_total": usage["total"],
        "total_cost_usd": usage["cost_usd"],
        "model": _metadata_value(latest, "model"),
        "last_reset": None,
        "last_provider_call_at": latest.created_at.isoformat() if latest is not None else None,
        "receipt_count": len(receipts),
        "missing": _cost_missing_fields(usage, latest),
        "warnings": [store_error] if store_error else [],
    }
    return CommandResult(
        payload=payload,
        shape="kv",
        text=_cost_text(payload),
        next_actions=_cost_next_actions(payload),
    )


def quota_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return configured provider quota references and explicit runtime gaps."""
    receipts, store_error = _receipts(env)
    latest = _latest_provider_receipt(receipts)
    providers = default_model_provider_registry().list()
    rows = [
        {
            "provider_id": provider.id,
            "provider": provider.provider,
            "budget_ref": provider.budget_ref,
            "quota_ref": provider.quota_ref,
            "quota_remaining": None,
            "budget_remaining": None,
        }
        for provider in providers
    ]
    payload: dict[str, object] = {
        "providers": rows,
        "active_provider": _metadata_value(latest, "provider_family"),
        "last_provider_call_at": latest.created_at.isoformat() if latest is not None else None,
        "missing": ["quota_remaining", "budget_remaining"],
        "warnings": [store_error] if store_error else [],
    }
    return CommandResult(
        payload=payload,
        shape="table",
        text=_quota_text(payload),
        next_actions=[
            NextAction(
                text="Open provider status",
                command="/provider",
                field="providers",
            )
        ],
    )


def _receipts(env: dict[str, str] | None) -> tuple[list[CapabilityReceipt], str | None]:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        return store.list_receipts(), None
    except LocalStoreError as error:
        return [], str(error)
    finally:
        store.close()


def _aggregate_usage(receipts: Iterable[CapabilityReceipt]) -> dict[str, int | float | None]:
    totals: dict[str, int | float | None] = {
        "input": 0,
        "output": 0,
        "total": 0,
        "cost_usd": None,
    }
    cost_usd = 0.0
    cost_seen = False
    for receipt in receipts:
        usage = receipt.result.metadata.get("usage")
        if isinstance(usage, dict):
            totals["input"] = int(totals["input"] or 0) + _int_usage(usage, "input")
            totals["output"] = int(totals["output"] or 0) + _int_usage(usage, "output")
            totals["total"] = int(totals["total"] or 0) + _int_usage(usage, "total")
        raw_cost = receipt.result.metadata.get("cost_usd")
        if isinstance(raw_cost, int | float):
            cost_seen = True
            cost_usd += float(raw_cost)
    if cost_seen:
        totals["cost_usd"] = round(cost_usd, 6)
    return totals


def _int_usage(usage: dict[Any, Any], key: str) -> int:
    raw = usage.get(key, usage.get(f"{key}_tokens", 0))
    return raw if isinstance(raw, int) else 0


def _latest_provider_receipt(receipts: Iterable[CapabilityReceipt]) -> CapabilityReceipt | None:
    provider_receipts = [
        receipt
        for receipt in receipts
        if isinstance(receipt.result.metadata.get("usage"), dict)
        or receipt.capability.startswith("model.")
    ]
    if not provider_receipts:
        return None
    return sorted(provider_receipts, key=lambda receipt: (receipt.created_at, receipt.id))[-1]


def _metadata_value(receipt: CapabilityReceipt | None, key: str) -> str | None:
    if receipt is None:
        return None
    value = receipt.result.metadata.get(key)
    return value if isinstance(value, str) else None


def _cost_missing_fields(
    usage: dict[str, int | float | None],
    latest: CapabilityReceipt | None,
) -> list[str]:
    missing: list[str] = []
    if usage["cost_usd"] is None:
        missing.append("total_cost_usd")
    if latest is None or _metadata_value(latest, "model") is None:
        missing.append("model")
    missing.append("last_reset")
    return missing


def _cost_next_actions(payload: dict[str, object]) -> list[NextAction]:
    if payload.get("total_cost_usd") is not None:
        return []
    return [
        NextAction(
            text="Inspect provider quota refs",
            command="/quota",
            field="total_cost_usd",
        )
    ]


def _cost_text(payload: dict[str, object]) -> str:
    lines = [
        "Cost And Usage",
        f"Tokens in: {payload['tokens_in']}",
        f"Tokens out: {payload['tokens_out']}",
        f"Tokens total: {payload['tokens_total']}",
        f"Total cost USD: {_display_missing(payload['total_cost_usd'])}",
        f"Model: {_display_missing(payload['model'])}",
        f"Last reset: {_display_missing(payload['last_reset'])}",
        f"Last provider call: {_display_missing(payload['last_provider_call_at'])}",
        f"Receipts scanned: {payload['receipt_count']}",
    ]
    _append_missing(lines, payload)
    return "\n".join(lines)


def _quota_text(payload: dict[str, object]) -> str:
    lines = ["Provider Quotas", ""]
    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        lines.append("- none")
    else:
        for row in providers:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {row['provider_id']}: budget={row['budget_ref'] or 'missing'} "
                f"quota={row['quota_ref'] or 'missing'} "
                f"remaining={_display_missing(row['quota_remaining'])}"
            )
    lines.extend(
        [
            "",
            f"Active provider: {_display_missing(payload['active_provider'])}",
            f"Last provider call: {_display_missing(payload['last_provider_call_at'])}",
        ]
    )
    _append_missing(lines, payload)
    return "\n".join(lines)


def _append_missing(lines: list[str], payload: dict[str, object]) -> None:
    missing = payload.get("missing")
    if isinstance(missing, list) and missing:
        lines.append("Missing data:")
        lines.extend(f"- {item}" for item in missing)
    warnings = payload.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)


def _display_missing(value: object) -> object:
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.isoformat()
    return value
