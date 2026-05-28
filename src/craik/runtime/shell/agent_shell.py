"""Interactive and one-shot Craik shell helpers."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable

from craik.runtime.backend.session import execute_prompt
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.dispatch import invoke_slash_command as _contract_invoke
from craik.runtime.i18n.messages import text as localize_text
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry
from craik.runtime.shell.contract_runtime.result_adapter import to_slash_command_result
from craik.runtime.shell.contract_runtime.run_helpers import run_command
from craik.runtime.shell.readiness import ReadinessReport, resolve_readiness


def render_status_card(report: ReadinessReport, *, env: dict[str, str] | None = None) -> str:
    """Render a compact launch status card."""
    lines = [
        localize_text("shell.title", env=env),
        f"{localize_text('shell.state', env=env)}: {report.state}",
        f"{localize_text('shell.home', env=env)}: {report.home}",
        f"{localize_text('shell.profile', env=env)}: {report.active_profile}",
        f"{localize_text('shell.model', env=env)}: "
        f"{report.active_model or localize_text('shell.not_selected', env=env)}",
    ]
    if report.missing:
        lines.append(f"{localize_text('shell.missing', env=env)}: {', '.join(report.missing)}")
    if report.warnings:
        lines.extend(
            f"{localize_text('shell.warning', env=env)}: {warning}"
            for warning in report.warnings
        )
    lines.append(f"{localize_text('shell.next_actions', env=env)}:")
    lines.extend(f"- {action}" for action in report.next_actions)
    lines.append(localize_text("shell.help_hint", env=env))
    return "\n".join(lines)


def one_shot_response(prompt: str, *, env: dict[str, str] | None = None) -> str:
    """Return the final one-shot shell response without extra shell decoration."""
    report = resolve_readiness(env)
    if report.state != "fully-ready":
        return localize_text(
            "shell.one_shot.not_ready",
            env=env,
            state=report.state,
            next_action=report.next_actions[0],
        )
    try:
        result = _execute_one_shot(prompt, env=env)
    except Exception as error:
        return f"One-shot execution failed: {error}"
    return result


def _execute_one_shot(prompt: str, *, env: dict[str, str] | None = None) -> str:
    payload = execute_prompt(prompt, env=env, source="cli").payload_with_events()
    return _one_shot_audit_text(payload)


def _one_shot_audit_text(payload: dict[str, object]) -> str:
    lines: list[str] = []
    final_text = _final_output_text(payload)
    if final_text:
        lines.append(final_text)
        lines.append("")
    run = payload.get("run")
    handoff = payload.get("handoff")
    receipt_ids = payload.get("receipt_ids")
    if not isinstance(run, dict):
        return final_text or "Audited run completed."
    status = payload.get("status") or run.get("status") or "completed"
    run_id = run.get("id")
    task_id = run.get("task_id")
    lines.append(f"Audited run `{run_id}` completed with status `{status}` for `{task_id}`.")
    if isinstance(handoff, dict) and handoff.get("id"):
        lines.append(f"Handoff: `{handoff['id']}`")
    if isinstance(receipt_ids, list):
        rendered_receipts = ", ".join(str(item) for item in receipt_ids if item) or "none"
        lines.append(f"Receipts: {rendered_receipts}")
    return "\n".join(lines)


def _final_output_text(payload: dict[str, object]) -> str:
    outputs = payload.get("run_outputs")
    if not isinstance(outputs, list):
        return ""
    for output in outputs:
        if not isinstance(output, dict):
            continue
        observed = output.get("observed_output")
        if not isinstance(observed, dict):
            continue
        text = observed.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def run_shell(
    *,
    env: dict[str, str] | None = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    stdin_isatty: bool | None = None,
    lines: Iterable[str] | None = None,
    registry: AutoSlashRegistry | None = None,
) -> int:
    """Run the Craik shell, falling back to a status card for noninteractive launch."""
    report = resolve_readiness(env)
    output_func(render_status_card(report, env=env))
    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    scripted = iter(lines) if lines is not None else None
    registry = registry or get_tui_registry()
    if not interactive and scripted is None:
        return 0

    while True:
        try:
            raw = next(scripted) if scripted is not None else input_func("craik> ")
        except (EOFError, StopIteration):
            return 0
        text = raw.strip()
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            output_func("Session ended.")
            return 0
        if text.startswith("/"):
            result = to_slash_command_result(
                _contract_invoke(text, registry=registry, env=env)
            )
            output_func(result.text)
            if result.exit_shell:
                return result.exit_code
            continue
        result = to_slash_command_result(run_command(text, env=env))
        output_func(result.text)
