from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.store.integrity import contract_hmac
from craik.tools.receipt_verifier import verify_receipt_bytes, verify_receipt_file


def test_receipt_verifier_accepts_valid_hmac(tmp_path: Path) -> None:
    key = _key_file(tmp_path)
    receipt = _signed_receipt(key)
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    result = verify_receipt_file(path, public_key_path=key)

    assert result.passed is True
    assert result.outcome == "pass"
    assert result.hmac_status == "verified"
    assert result.receipt_id == "receipt_v0125"


def test_receipt_verifier_detects_hmac_tamper(tmp_path: Path) -> None:
    key = _key_file(tmp_path)
    receipt = _signed_receipt(key)
    receipt["result"]["summary"] = "tampered"

    result = verify_receipt_bytes(json.dumps(receipt).encode(), public_key_path=key)

    assert result.passed is False
    assert result.outcome == "tampered_hmac"
    assert result.hmac_status == "tampered"
    assert "receipt_hmac_mismatch" in result.failures


def test_receipt_verifier_rejects_unredacted_metadata(tmp_path: Path) -> None:
    key = _key_file(tmp_path)
    receipt = _signed_receipt(key)
    receipt["result"]["metadata"]["redacted"] = False
    receipt["receipt_hmac"] = contract_hmac(receipt, _hmac_key(key))

    result = verify_receipt_bytes(json.dumps(receipt).encode(), public_key_path=key)

    assert result.passed is False
    assert result.redaction_status == "failed"
    assert "result_metadata_marked_unredacted" in result.failures


def test_receipt_verifier_checks_shell_side_logs(tmp_path: Path) -> None:
    key = _key_file(tmp_path)
    side_log_base = tmp_path / "shell-output"
    side_log_base.mkdir()
    stdout = b"hello\n"
    stderr = b""
    stdout_sha = _sha(stdout)
    stderr_sha = _sha(stderr)
    (side_log_base / f"{stdout_sha}.stdout.log").write_bytes(stdout)
    (side_log_base / f"{stderr_sha}.stderr.log").write_bytes(stderr)
    receipt = {
        "schema": "craik.shell_invocation_receipt",
        "receipt_id": "shell_receipt",
        "stdout_sha256": stdout_sha,
        "stderr_sha256": stderr_sha,
        "redactions_applied": [],
        "receipt_hmac": None,
    }
    receipt["receipt_hmac"] = contract_hmac(receipt, _hmac_key(key))

    result = verify_receipt_bytes(
        json.dumps(receipt).encode(),
        public_key_path=key,
        side_log_base=side_log_base,
    )

    assert result.passed is True
    assert result.side_log_status == "verified"


def test_receipt_verifier_reports_side_log_tamper(tmp_path: Path) -> None:
    key = _key_file(tmp_path)
    side_log_base = tmp_path / "shell-output"
    side_log_base.mkdir()
    stdout_sha = _sha(b"expected")
    (side_log_base / f"{stdout_sha}.stdout.log").write_bytes(b"tampered")
    receipt = {
        "receipt_id": "shell_receipt",
        "stdout_sha256": stdout_sha,
        "redacted": True,
        "receipt_hmac": None,
    }
    receipt["receipt_hmac"] = contract_hmac(receipt, _hmac_key(key))

    result = verify_receipt_bytes(
        json.dumps(receipt).encode(),
        public_key_path=key,
        side_log_base=side_log_base,
    )

    assert result.passed is False
    assert result.side_log_status == "failed"
    assert "stdout_side_log_sha_mismatch" in result.failures


def test_receipt_verifier_rejects_invalid_side_log_digest_before_path_join(
    tmp_path: Path,
) -> None:
    key = _key_file(tmp_path)
    side_log_base = tmp_path / "shell-output"
    side_log_base.mkdir()
    receipt = {
        "receipt_id": "shell_receipt",
        "stdout_sha256": "../../outside",
        "redacted": True,
        "receipt_hmac": None,
    }
    receipt["receipt_hmac"] = contract_hmac(receipt, _hmac_key(key))

    result = verify_receipt_bytes(
        json.dumps(receipt).encode(),
        public_key_path=key,
        side_log_base=side_log_base,
    )

    assert result.passed is False
    assert result.side_log_status == "failed"
    assert "stdout_sha256_invalid_format" in result.failures
    assert not (tmp_path / "outside.stdout.log").exists()


def test_receipt_verify_cli_outputs_json_and_exit_code(tmp_path: Path) -> None:
    key = _key_file(tmp_path)
    receipt = _signed_receipt(key)
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["receipt", "verify", str(path), "--public-key", str(key)],
    )

    assert result.exception is None
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["hmac_status"] == "verified"


def test_receipt_verify_cli_fails_on_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["receipt", "verify", str(path)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["outcome"] == "fail"


def test_receipt_verifier_auto_discovers_craik_home_key(tmp_path: Path) -> None:
    home = tmp_path / "craik-home"
    key_dir = home / "secrets"
    key_dir.mkdir(parents=True)
    key = key_dir / "instruction-approval-hmac.key"
    key.write_text("receipt-verifier-test-key\n", encoding="utf-8")
    receipt = _signed_receipt(key)

    result = verify_receipt_bytes(
        json.dumps(receipt).encode(),
        auto_discover=True,
        env={"CRAIK_HOME": str(home)},
    )

    assert result.passed is True
    assert result.hmac_status == "verified"


def _signed_receipt(key_path: Path) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema": "craik.plugin_receipt",
        "id": "receipt_v0125",
        "result": {
            "status": "passed",
            "summary": "verified",
            "metadata": {"redacted": True},
        },
        "redacted": True,
        "receipt_hmac": None,
    }
    receipt["receipt_hmac"] = contract_hmac(receipt, _hmac_key(key_path))
    return receipt


def _key_file(tmp_path: Path) -> Path:
    path = tmp_path / "public.key"
    path.write_text("receipt-verifier-test-key\n", encoding="utf-8")
    return path


def _hmac_key(path: Path) -> bytes:
    import hashlib

    return hashlib.sha256(path.read_text(encoding="utf-8").strip().encode()).digest()


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
