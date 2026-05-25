"""Receipt persistence and lookup helpers."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypedDict

from craik.contracts.models import CapabilityReceipt
from craik.runtime.contract import CommandResult
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.runners.runner_metadata import runner_metadata_from_receipt_metadata
from craik.runtime.store import LocalStore
from craik.tools.receipt_verifier import verify_receipt_bytes, verify_receipt_file


class ReceiptLinks(TypedDict):
    """Normalized references connected to a capability receipt."""

    task_id: str
    policy_profile: str
    fail_open: bool
    policy_envelope_id: str | None
    handoff_ids: list[str]
    runner_metadata: dict[str, Any] | None


class ReceiptStoreError(RuntimeError):
    """Base error for receipt store failures."""


class ReceiptNotFoundError(ReceiptStoreError):
    """Raised when a requested receipt does not exist."""


class ReceiptStore:
    """Task-aware receipt queries over the local runtime store."""

    def __init__(self, store: LocalStore) -> None:
        self._store = store

    def record_receipt(self, receipt: CapabilityReceipt) -> CapabilityReceipt:
        """Persist a validated receipt and return the stored model."""
        return self._store.put_receipt(receipt)

    def get_receipt(self, receipt_id: str) -> CapabilityReceipt | None:
        """Load one receipt by id."""
        return self._store.get_receipt(receipt_id)

    def require_receipt(self, receipt_id: str) -> CapabilityReceipt:
        """Load one receipt by id or raise a clear error."""
        receipt = self.get_receipt(receipt_id)
        if receipt is None:
            raise ReceiptNotFoundError(f"unknown receipt: {receipt_id}")
        return receipt

    def list_receipts(
        self,
        *,
        task_id: str | None = None,
        policy_id: str | None = None,
        handoff_id: str | None = None,
    ) -> list[CapabilityReceipt]:
        """List receipts with optional task, policy envelope, and handoff filters."""
        receipts: Iterable[CapabilityReceipt] = self._store.list_receipts()
        if task_id is not None:
            receipts = (receipt for receipt in receipts if receipt.task_id == task_id)
        if policy_id is not None:
            receipts = (
                receipt
                for receipt in receipts
                if receipt_links(receipt)["policy_envelope_id"] == policy_id
            )
        if handoff_id is not None:
            receipts = (
                receipt
                for receipt in receipts
                if handoff_id in receipt_links(receipt)["handoff_ids"]
            )
        return list(receipts)


def receipt_links(receipt: CapabilityReceipt) -> ReceiptLinks:
    """Return normalized linkage fields carried by a receipt."""
    metadata = receipt.result.metadata
    return {
        "task_id": receipt.task_id,
        "policy_profile": receipt.policy_profile,
        "fail_open": receipt.fail_open,
        "policy_envelope_id": _optional_string(metadata.get("policy_envelope_id")),
        "handoff_ids": _string_list(metadata.get("handoff_ids")),
        "runner_metadata": runner_metadata_from_receipt_metadata(metadata),
    }


def receipts_list_result(
    *,
    task_id: str | None = None,
    policy_id: str | None = None,
    handoff_id: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return persisted capability receipts."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        receipt_store = ReceiptStore(store)
        receipts = receipt_store.list_receipts(
            task_id=task_id,
            policy_id=policy_id,
            handoff_id=handoff_id,
        )
    finally:
        store.close()
    return CommandResult(
        payload=[receipt.model_dump(mode="json", by_alias=True) for receipt in receipts],
        shape="card_list",
        empty_state_message="No capability receipts found.",
    )


def receipts_show_result(receipt_id: str, *, env: dict[str, str] | None = None) -> CommandResult:
    """Return one persisted capability receipt."""
    store = LocalStore.from_paths(resolve_craik_paths(env))
    try:
        store.initialize()
        receipt_store = ReceiptStore(store)
        receipt = receipt_store.require_receipt(receipt_id)
    except ReceiptNotFoundError as error:
        raise ValueError(str(error)) from None
    finally:
        store.close()
    return CommandResult(payload=receipt.model_dump(mode="json", by_alias=True), shape="card")


def receipts_verify_result(
    path: str,
    *,
    public_key: Path | None = None,
    auto_discover: bool = False,
    side_log_base: Path | None = None,
) -> CommandResult:
    """Verify a receipt JSON file without trusting the producing runtime."""
    if path == "-":
        verification = verify_receipt_bytes(
            sys.stdin.buffer.read(),
            public_key_path=public_key,
            auto_discover=auto_discover,
            side_log_base=side_log_base,
        )
    else:
        verification = verify_receipt_file(
            path,
            public_key_path=public_key,
            auto_discover=auto_discover,
            side_log_base=side_log_base,
        )
    return CommandResult(
        payload=verification.as_dict(),
        shape="kv",
        exit_code=0 if verification.passed else 1,
    )


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []
