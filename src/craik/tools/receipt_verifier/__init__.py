"""Standalone receipt verification helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from craik.runtime.store.integrity import contract_hmac

# Filename only; actual HMAC key material is read from operator-controlled state.
_HMAC_SECRET_FILENAME = "instruction-approval-hmac.key"  # nosec B105


@dataclass(frozen=True)
class VerificationResult:
    """Structured result for one receipt verification."""

    passed: bool
    outcome: str
    receipt_id: str | None
    hmac_status: str
    redaction_status: str
    side_log_status: str
    failures: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-ready result data."""
        return asdict(self)


def verify_receipt_file(
    path: str | Path,
    *,
    public_key_path: str | Path | None = None,
    auto_discover: bool = False,
    side_log_base: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> VerificationResult:
    """Verify one receipt JSON file."""
    data = Path(path).read_bytes()
    return verify_receipt_bytes(
        data,
        public_key_path=public_key_path,
        auto_discover=auto_discover,
        side_log_base=side_log_base,
        env=env,
    )


def verify_receipt_bytes(
    data: bytes,
    *,
    public_key_path: str | Path | None = None,
    auto_discover: bool = False,
    side_log_base: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> VerificationResult:
    """Verify one receipt JSON payload without importing the runtime store."""
    failures: list[str] = []
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return _result(
            receipt_id=None,
            hmac_status="unknown",
            redaction_status="unknown",
            side_log_status="unknown",
            failures=[f"malformed_json: {error}"],
        )
    if not isinstance(payload, dict):
        return _result(
            receipt_id=None,
            hmac_status="unknown",
            redaction_status="unknown",
            side_log_status="unknown",
            failures=["receipt_json_must_be_object"],
        )

    receipt_id = _receipt_id(payload)
    hmac_status = _hmac_status(
        payload,
        public_key_path=public_key_path,
        auto_discover=auto_discover,
        env=env,
        failures=failures,
    )
    redaction_status = _redaction_status(payload, failures)
    side_log_status = _side_log_status(payload, side_log_base, failures)
    return _result(
        receipt_id=receipt_id,
        hmac_status=hmac_status,
        redaction_status=redaction_status,
        side_log_status=side_log_status,
        failures=failures,
    )


def _hmac_status(
    payload: dict[str, Any],
    *,
    public_key_path: str | Path | None,
    auto_discover: bool,
    env: dict[str, str] | None,
    failures: list[str],
) -> str:
    supplied = payload.get("receipt_hmac")
    if not isinstance(supplied, str) or not supplied:
        failures.append("receipt_hmac_missing")
        return "unverified"
    key = _hmac_key(public_key_path, auto_discover=auto_discover, env=env)
    if key is None:
        failures.append("hmac_key_unavailable")
        return "unverified"
    expected = contract_hmac(payload, key)
    if supplied != expected:
        failures.append("receipt_hmac_mismatch")
        return "tampered"
    return "verified"


def _hmac_key(
    public_key_path: str | Path | None,
    *,
    auto_discover: bool,
    env: dict[str, str] | None,
) -> bytes | None:
    key_path = Path(public_key_path) if public_key_path is not None else None
    if key_path is None and auto_discover:
        values = os.environ if env is None else env
        home = Path(values.get("CRAIK_HOME", Path.home() / ".craik"))
        key_path = home / "secrets" / _HMAC_SECRET_FILENAME
    if key_path is None or not key_path.exists():
        return None
    raw = key_path.read_text(encoding="utf-8").strip()
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _redaction_status(payload: dict[str, Any], failures: list[str]) -> str:
    if payload.get("redacted") is False:
        failures.append("receipt_marked_unredacted")
        return "failed"
    result = payload.get("result")
    if isinstance(result, dict):
        metadata = result.get("metadata")
        if isinstance(metadata, dict) and metadata.get("redacted") is False:
            failures.append("result_metadata_marked_unredacted")
            return "failed"
    return "verified"


def _side_log_status(
    payload: dict[str, Any],
    side_log_base: str | Path | None,
    failures: list[str],
) -> str:
    hashes = {
        "stdout": payload.get("stdout_sha256"),
        "stderr": payload.get("stderr_sha256"),
    }
    expected = {stream: digest for stream, digest in hashes.items() if isinstance(digest, str)}
    if not expected:
        return "not_applicable"
    if side_log_base is None:
        return "not_checked"
    base = Path(side_log_base)
    for stream, digest in expected.items():
        path = base / f"{digest}.{stream}.log"
        if not path.exists():
            failures.append(f"{stream}_side_log_missing")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            failures.append(f"{stream}_side_log_sha_mismatch")
    return "verified" if not any("side_log" in failure for failure in failures) else "failed"


def _receipt_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("id") or payload.get("receipt_id")
    return str(value) if value else None


def _result(
    *,
    receipt_id: str | None,
    hmac_status: str,
    redaction_status: str,
    side_log_status: str,
    failures: list[str],
) -> VerificationResult:
    if "receipt_hmac_mismatch" in failures:
        outcome = "tampered_hmac"
    elif failures:
        outcome = "fail"
    else:
        outcome = "pass"
    return VerificationResult(
        passed=not failures,
        outcome=outcome,
        receipt_id=receipt_id,
        hmac_status=hmac_status,
        redaction_status=redaction_status,
        side_log_status=side_log_status,
        failures=failures,
    )
