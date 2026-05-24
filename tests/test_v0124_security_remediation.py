from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import PluginReceipt, ReceiptResult
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_modals import (
    ReceiptDetailModal,
    _receipt_integrity_status,
)
from craik.runtime.shell.textual_widgets.craik_input import CraikInput, slash_command_conversion
from craik.runtime.shell.textual_widgets.slash_renderers import render_slash_payload
from craik.runtime.shell.textual_widgets.status_bar import StatusBar
from craik.runtime.shell.textual_widgets.toast_queue import ToastQueue, render_toast_queue
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


@pytest.mark.parametrize(
    "command",
    [
        "/clear",
        "/policy reset",
        "/migrate apply",
        "/agent delete agent_alpha",
        "/session delete session_alpha",
        "/receipts purge",
    ],
)
def test_destructive_slash_commands_open_confirmation(command: str, tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            app.query_one("#input", CraikInput).value = command
            await pilot.press("enter")
            assert app.screen.__class__.__name__ == "ConfirmModal"

    asyncio.run(run())


def test_plugin_receipt_detail_status_detects_tampered_hmac(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        original = _plugin_receipt()
        store.put_plugin_receipt(original)
        receipt = store.get_plugin_receipt(original.id)
        assert receipt is not None
        tampered = receipt.model_copy(update={"result": _result("tampered")})

        assert _receipt_integrity_status(store, receipt) == "verified hmac"
        assert _receipt_integrity_status(store, tampered) == "tampered hmac"
    finally:
        store.close()


def test_receipt_detail_and_logout_markup_escape(tmp_path: Path) -> None:
    env = _env(tmp_path)
    malicious = "[red]bad[/red]"
    store = LocalStore.from_paths(ensure_craik_home(env))
    store.initialize()
    store.close()

    assert "\\[red]" in ReceiptDetailModal(malicious, env=env)._detail_text()


def test_toast_and_structured_renderer_escape_markup() -> None:
    queue = ToastQueue()
    queue.push("[red]bad[/red]", severity="warning")
    assert "\\[red]" in render_toast_queue(queue.notices)

    table = render_slash_payload([{"value": "[red]bad[/red]"}], shape="table")
    console = Console(record=True, width=80)
    console.print(table)
    assert "[red]bad[/red]" in console.export_text()


def test_status_bar_escapes_session_and_model_markup() -> None:
    from craik.runtime.shell.readiness import ReadinessReport

    bar = StatusBar()
    bar.update_status(
        ReadinessReport(
            state="unconfigured",
            home=Path("/tmp/craik"),
            initialized=False,
            operator_required=False,
            operator_authenticated=False,
            provider_configured=False,
            local_model_configured=False,
            active_profile="default",
            active_model="[red]model[/red]",
        ),
        session_name="[blue]session[/blue]",
    )

    assert "[red]model[/red]" in bar.current_status
    assert "[blue]session[/blue]" in bar.current_status


def test_forgot_slash_narrows_natural_language_false_positives() -> None:
    assert slash_command_conversion("provider") == "/provider"
    assert slash_command_conversion("memory leak") is None
    assert slash_command_conversion("status update") is None
    assert slash_command_conversion("exit strategy") is None
    assert slash_command_conversion("auth bug repro") is None


def test_cli_login_issuer_help_is_clean() -> None:
    result = CliRunner().invoke(app, ["login", "--issuer", "--help"])

    assert result.exit_code == 0
    assert "Option `--issuer`" in result.output
    assert "Traceback" not in result.output


def _plugin_receipt() -> PluginReceipt:
    return PluginReceipt.model_validate(
        {
            "id": "plugin_receipt_docs_reconcile",
            "task_id": "task_docs_reconcile",
            "actor": "agent:test",
            "plugin_descriptor_id": "plugin_docs_reconcile",
            "plugin_probation_id": "plugin_probation_docs_reconcile",
            "action": "docs.reconcile",
            "capability_grant_ids": ["grant_docs_write"],
            "trust_boundary": "project",
            "result": _result("Plugin action completed."),
            "evidence_ids": ["evidence_readme_status"],
            "handoff_ids": ["handoff_docs_reconcile"],
            "redacted": True,
            "created_at": "2026-05-16T16:20:00Z",
        }
    )


def _result(summary: str) -> ReceiptResult:
    return ReceiptResult(status="passed", summary=summary, metadata={"redacted": True})
