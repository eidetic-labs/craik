"""Receipt detail modal built on the canonical record display primitive."""

from __future__ import annotations

from typing import Any, cast

from craik.runtime.paths import resolve_craik_paths
from craik.runtime.shell.modals.record_display import RecordDisplayModal, RecordDisplayRequest
from craik.runtime.shell.textual_widgets.glyph_palette import RECEIPT_OK
from craik.runtime.store import LocalStore
from craik.runtime.store.receipt_integrity import contract_receipt_hmac_status


class ReceiptDetailModal(RecordDisplayModal):
    """Display audit details for one receipt id."""

    def __init__(self, receipt_id: str, *, env: dict[str, str] | None = None) -> None:
        super().__init__(
            RecordDisplayRequest(
                title=f"{RECEIPT_OK} Receipt details",
                record=receipt_detail_record(receipt_id, env=env),
                actions=["close"],
            )
        )


def receipt_detail_record(receipt_id: str, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a redacted display record for a receipt id."""
    store = _open_store(env)
    try:
        receipt = _find_receipt(store, receipt_id)
        if receipt is None:
            return {"id": receipt_id, "found": False, "message": "receipt not found"}
        integrity_status = _receipt_integrity_status(store, receipt)
    finally:
        store.close()
    result = getattr(receipt, "result", None)
    return {
        "id": receipt_id,
        "found": True,
        "integrity": integrity_status,
        "status": str(getattr(result, "status", "unknown")),
        "summary": str(getattr(result, "summary", "") or "not recorded"),
    }


def _open_store(env: dict[str, str] | None) -> LocalStore:
    paths = resolve_craik_paths(env)
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _find_receipt(store: LocalStore, receipt_id: str) -> object | None:
    for method_name in ("list_receipts", "list_plugin_receipts", "list_gateway_receipts"):
        method = getattr(store, method_name, None)
        if method is None:
            continue
        for receipt in method():
            if getattr(receipt, "id", None) == receipt_id:
                return cast(object, receipt)
    return None


def _receipt_integrity_status(store: LocalStore, receipt: object) -> str:
    hmac = getattr(receipt, "receipt_hmac", None)
    if hmac:
        try:
            return f"{contract_receipt_hmac_status(store, receipt)} hmac"  # type: ignore[arg-type]
        except (AttributeError, TypeError, ValueError):
            return "tampered hmac"
    receipt_hash = getattr(receipt, "self_hash", None)
    if receipt_hash:
        return "verified receipt chain"
    return "unverified"
