"""Receipt integrity read helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from craik.contracts.models import PluginReceipt
from craik.runtime.store.integrity import (
    IntegrityStore,
    hmac_key_for_store,
    verify_contract_hmac,
)

ReceiptHmacStatus = Literal["verified", "unverified", "tampered"]


@dataclass(frozen=True)
class PluginReceiptReadResult:
    receipt: PluginReceipt
    hmac_status: ReceiptHmacStatus


def plugin_receipt_hmac_status(
    store: IntegrityStore,
    receipt: PluginReceipt,
) -> ReceiptHmacStatus:
    if receipt.receipt_hmac is None:
        return "unverified"
    payload = receipt.model_dump(mode="json", by_alias=True)
    if verify_contract_hmac(payload, hmac_key_for_store(store)):
        return "verified"
    return "tampered"
