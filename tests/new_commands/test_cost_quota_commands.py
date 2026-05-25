"""Coverage for v0.12.8 cost and quota slash commands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from craik.cli import app
from craik.contracts.models import CapabilityReceipt, ReceiptResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.commands import cost_result, quota_result
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore

SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "snapshots" / "slash"


def test_cost_slash_command_renders_missing_data_snapshot(tmp_path: Path) -> None:
    result = dispatch_slash_command("/cost", env={"CRAIK_HOME": str(tmp_path)})

    snapshot = SNAPSHOT_ROOT / "cost" / "width-80.txt"

    assert result.exit_code == 0
    assert result.payload["tokens_total"] == 0
    assert result.payload["total_cost_usd"] is None
    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_quota_slash_command_renders_provider_refs_snapshot(tmp_path: Path) -> None:
    result = dispatch_slash_command("/quota", env={"CRAIK_HOME": str(tmp_path)})

    snapshot = SNAPSHOT_ROOT / "quota" / "width-80.txt"

    assert result.exit_code == 0
    assert result.payload["providers"]
    assert result.payload["missing"] == ["quota_remaining", "budget_remaining"]
    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_cost_result_aggregates_provider_receipt_usage(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        store.put_receipt(_usage_receipt("receipt_one", 10, 4, 14, cost_usd=0.002))
        store.put_receipt(_usage_receipt("receipt_two", 7, 3, 10, cost_usd=0.001))
    finally:
        store.close()

    result = cost_result(env)

    assert result.payload["tokens_in"] == 17
    assert result.payload["tokens_out"] == 7
    assert result.payload["tokens_total"] == 24
    assert result.payload["total_cost_usd"] == 0.003
    assert result.payload["model"] == "gpt-test"
    assert "total_cost_usd" not in result.payload["missing"]


def test_quota_result_reports_active_provider_from_receipts(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        store.put_receipt(_usage_receipt("receipt_one", 1, 1, 2))
    finally:
        store.close()

    result = quota_result(env)

    assert result.payload["active_provider"] == "openai"
    assert any(row["provider_id"] == "provider_openai" for row in result.payload["providers"])


def test_cost_and_quota_are_registered_as_derived_slash_commands() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/cost") is not None
    assert registry.spec_by_name("/quota") is not None


def _usage_receipt(
    receipt_id: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    *,
    cost_usd: float | None = None,
) -> CapabilityReceipt:
    metadata: dict[str, object] = {
        "provider_family": "openai",
        "model": "gpt-test",
        "usage": {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
        },
    }
    if cost_usd is not None:
        metadata["cost_usd"] = cost_usd
    return CapabilityReceipt(
        id=receipt_id,
        task_id="task_usage",
        actor="craik",
        capability="model.chat",
        target="gpt-test",
        policy_profile="strict",
        reason="Provider request normalized and redacted.",
        result=ReceiptResult(
            status="passed",
            summary="Provider call completed.",
            metadata=metadata,
        ),
        created_at=datetime.now(UTC),
    )
