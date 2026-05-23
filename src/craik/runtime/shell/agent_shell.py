"""Interactive and one-shot Craik shell helpers."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable

from craik.runtime.i18n.messages import text as localize_text
from craik.runtime.shell.readiness import ReadinessReport, resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command


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
    return localize_text(
        "shell.one_shot.queued",
        env=env,
        model=report.active_model,
        prompt=prompt.strip(),
    )


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
    output_func(render_status_card(report, env=env))
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
