"""Interactive and one-shot Craik shell helpers."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable

from craik.runtime.shell.readiness import ReadinessReport, resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command


def render_status_card(report: ReadinessReport) -> str:
    """Render a compact launch status card."""
    lines = [
        "Craik Agent Shell",
        f"State: {report.state}",
        f"Home: {report.home}",
        f"Profile: {report.active_profile}",
        f"Model: {report.active_model or 'not selected'}",
    ]
    if report.missing:
        lines.append(f"Missing: {', '.join(report.missing)}")
    if report.warnings:
        lines.extend(f"Warning: {warning}" for warning in report.warnings)
    lines.append("Next actions:")
    lines.extend(f"- {action}" for action in report.next_actions)
    lines.append("Type /help for commands or /exit to quit.")
    return "\n".join(lines)


def one_shot_response(prompt: str, *, env: dict[str, str] | None = None) -> str:
    """Return the final one-shot shell response without extra shell decoration."""
    report = resolve_readiness(env)
    if report.state != "fully-ready":
        return (
            "Craik is not ready for one-shot model execution. "
            f"State: {report.state}. Next: {report.next_actions[0]}"
        )
    return f"One-shot execution is queued for {report.active_model}: {prompt.strip()}"


def run_shell(
    *,
    env: dict[str, str] | None = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    stdin_isatty: bool | None = None,
    lines: Iterable[str] | None = None,
) -> int:
    """Run the Craik shell, falling back to a status card for noninteractive launch."""
    report = resolve_readiness(env)
    output_func(render_status_card(report))
    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    scripted = iter(lines) if lines is not None else None
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
            result = dispatch_slash_command(text, env=env)
            output_func(result.text)
            if result.exit_shell:
                return result.exit_code
            continue
        output_func(one_shot_response(text, env=env))
