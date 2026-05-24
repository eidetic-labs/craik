from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from craik.runtime.shell.textual_modals import ReceiptDetailModal, _receipt_integrity_status


class _FakeReceipt:
    def __init__(
        self,
        *,
        receipt_hmac: str | None = None,
        self_hash: str | None = None,
    ) -> None:
        self.receipt_hmac = receipt_hmac
        self.self_hash = self_hash


class _FakeStore:
    def close(self) -> None:
        pass


def test_receipt_integrity_status_calls_hmac_verifier() -> None:
    store = _FakeStore()
    receipt = _FakeReceipt(receipt_hmac="valid-hmac")

    with patch(
        "craik.runtime.shell.textual_modals.contract_receipt_hmac_status",
        return_value="verified",
    ) as verify:
        result = _receipt_integrity_status(store, receipt)  # type: ignore[arg-type]

    verify.assert_called_once_with(store, receipt)
    assert result == "verified hmac"


def test_receipt_integrity_status_reports_tampered_hmac() -> None:
    store = _FakeStore()
    receipt = _FakeReceipt(receipt_hmac="tampered-hmac")

    with patch(
        "craik.runtime.shell.textual_modals.contract_receipt_hmac_status",
        side_effect=ValueError("HMAC mismatch"),
    ):
        result = _receipt_integrity_status(store, receipt)  # type: ignore[arg-type]

    assert result == "tampered hmac"
    assert "verified" not in result


def test_receipt_integrity_status_reports_unverified_without_hmac_or_hash() -> None:
    store = _FakeStore()
    receipt = _FakeReceipt()

    assert _receipt_integrity_status(store, receipt) == "unverified"  # type: ignore[arg-type]


def test_receipt_integrity_status_treats_verifier_exceptions_as_tamper() -> None:
    store = _FakeStore()
    receipt = _FakeReceipt(receipt_hmac="hmac")

    for exception_type in (AttributeError, TypeError, ValueError):
        with patch(
            "craik.runtime.shell.textual_modals.contract_receipt_hmac_status",
            side_effect=exception_type("boom"),
        ):
            result = _receipt_integrity_status(store, receipt)  # type: ignore[arg-type]

        assert result == "tampered hmac"


def test_receipt_detail_escapes_adversarial_receipt_id(tmp_path: Path) -> None:
    adversarial_id = "[red blink]injection[/red blink]"
    modal = ReceiptDetailModal(adversarial_id, env={"CRAIK_HOME": str(tmp_path)})

    with patch("craik.runtime.shell.textual_modals._open_store", return_value=_FakeStore()):
        with patch(
            "craik.runtime.shell.textual_modals._find_receipt",
            return_value=None,
        ):
            text = modal._detail_text()

    assert "\\[red blink]" in text
    assert "`[red blink]" not in text


def test_receipt_detail_escapes_result_fields(tmp_path: Path) -> None:
    modal = ReceiptDetailModal("receipt-1", env={"CRAIK_HOME": str(tmp_path)})
    receipt = type(
        "Receipt",
        (),
        {
            "receipt_hmac": None,
            "self_hash": "hash",
            "result": type(
                "Result",
                (),
                {"status": "[red]passed[/red]", "summary": "[blue]summary[/blue]"},
            )(),
        },
    )()

    with patch("craik.runtime.shell.textual_modals._open_store", return_value=_FakeStore()):
        with patch(
            "craik.runtime.shell.textual_modals._find_receipt",
            return_value=receipt,
        ):
            text = modal._detail_text()

    assert "[red]passed[/red]" not in text
    assert "\\[red]passed\\[/red]" in text
    assert "\\[blue]summary\\[/blue]" in text
