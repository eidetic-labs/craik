"""Rich renderers for the Textual transcript."""

from __future__ import annotations

import json
import re
from datetime import datetime

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

USER_STYLE = "#B4ACE6"
MODEL_STYLE = "#7BC6A4"
CLAUDE_STYLE = "#9DCBFF"
WARNING_STYLE = "#E4B363"
ERROR_STYLE = "#E48787"
MUTED_STYLE = "#8F8F8F"
TEXT_STYLE = "#D7F4E8"


def render_user_message(text: str) -> RenderableType:
    """Render an operator prompt as a visually distinct transcript turn."""
    return Panel(
        Text(text, style="#F2F0FF", no_wrap=False),
        title=_header("You"),
        title_align="left",
        border_style=USER_STYLE,
        padding=(1, 2),
    )


def render_model_message(text: str, *, model_label: str = "Model") -> RenderableType:
    """Render model output with Markdown and fenced-code highlighting."""
    body = text.strip() or "(empty response)"
    return Group(
        Panel(
            Markdown(body, code_theme="monokai", hyperlinks=True),
            title=_header(model_label),
            title_align="left",
            border_style=MODEL_STYLE,
            padding=(1, 2),
        ),
        Text(""),
    )


def render_claude_event(message: str) -> RenderableType:
    """Render Claude Code progress with event-aware highlighting."""
    normalized = message.strip()
    if not normalized:
        return _event_panel("Claude Code", Text("No activity yet.", style=MUTED_STYLE), MUTED_STYLE)
    if _looks_like_diff(normalized):
        return _event_panel(
            "Claude Code diff",
            Syntax(normalized, "diff", theme="monokai", word_wrap=True),
            CLAUDE_STYLE,
        )
    command = _extract_backticked_after(normalized, ": `")
    if command and _looks_like_tool_message(normalized, "Bash"):
        return _event_panel(
            "Claude Code command",
            Group(
                Text(_strip_backticked_tail(normalized), style=MUTED_STYLE),
                Syntax(command, "bash", theme="monokai", word_wrap=True),
            ),
            CLAUDE_STYLE,
        )
    if _looks_like_json(normalized):
        return _event_panel(
            "Claude Code JSON",
            Syntax(_pretty_json(normalized), "json", theme="monokai", word_wrap=True),
            CLAUDE_STYLE,
        )
    style = _claude_event_style(normalized)
    if style in {WARNING_STYLE, ERROR_STYLE}:
        title = "Claude Code blocked" if style == ERROR_STYLE else "Claude Code attention"
        return _event_panel(title, Text(normalized, style=style), style)
    if normalized.startswith("Claude Code is using `"):
        return _event_panel(
            "Claude Code tool",
            Markdown(_event_markdown(normalized), code_theme="monokai"),
            CLAUDE_STYLE,
        )
    return _event_panel(
        "Claude Code event",
        Markdown(_event_markdown(normalized), code_theme="monokai"),
        CLAUDE_STYLE,
    )


def render_run_summary(
    payload: dict[str, object],
    *,
    title: str = "Audited run summary",
) -> RenderableType:
    """Render a final audited run payload as an operator summary card."""
    raw_run = payload.get("run")
    raw_handoff = payload.get("handoff")
    raw_outputs = payload.get("run_outputs")
    run: dict[str, object] = raw_run if isinstance(raw_run, dict) else {}
    handoff: dict[str, object] = raw_handoff if isinstance(raw_handoff, dict) else {}
    outputs: list[object] = raw_outputs if isinstance(raw_outputs, list) else []
    activity = _summary_activity(outputs)
    status = str(payload.get("status") or run.get("status") or "unknown")
    border = (
        ERROR_STYLE
        if status == "failed"
        else WARNING_STYLE
        if status == "interrupted"
        else MODEL_STYLE
    )

    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="bold")
    facts.add_column()
    facts.add_row("Status", status)
    facts.add_row("Task", str(run.get("task_id") or "unknown"))
    facts.add_row("Run", str(run.get("id") or "unknown"))
    facts.add_row("Handoff", str(handoff.get("id") or "unknown"))

    receipts = payload.get("receipt_ids")
    if isinstance(receipts, list) and receipts:
        facts.add_row("Receipts", ", ".join(str(item) for item in receipts))

    files = _string_list(activity.get("files"))
    commands = _string_list(activity.get("commands"))
    tools = _string_list(activity.get("tools"))
    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold")
    details.add_column()
    details.add_row("Tools", ", ".join(tools) if tools else "none observed")
    details.add_row("Files", ", ".join(files) if files else "none observed")
    details.add_row("Commands", "\n".join(commands) if commands else "none observed")

    blocks: list[RenderableType] = [facts, Text(""), details]
    final_text = _summary_final_text(outputs)
    if final_text:
        blocks.extend([Text(""), Text("Final output", style=f"bold {MODEL_STYLE}")])
        blocks.append(Markdown(final_text, code_theme="monokai"))

    next_commands = payload.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        blocks.extend([Text(""), Text("Next", style=f"bold {CLAUDE_STYLE}")])
        blocks.append(Markdown("\n".join(f"- `{item}`" for item in next_commands if item)))

    return Group(
        Panel(
            Group(*blocks),
            title=_header(title),
            title_align="left",
            border_style=border,
            padding=(1, 2),
        ),
        Text(""),
    )


def render_claude_run_summary(payload: dict[str, object]) -> RenderableType:
    """Render the final Claude Code run payload as an operator summary card."""
    return render_run_summary(payload, title="Claude Code run summary")


def plain_transcript_label(role: str) -> str:
    """Return a stable plain-text role label for copied/exported transcript rows."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"{role} [{timestamp}]"


def _header(label: str) -> str:
    return f"{label} {datetime.now().strftime('%H:%M:%S')}"


def _label(label: str, style: str) -> Text:
    return Text(_header(label), style=f"bold {style}")


def _event_panel(title: str, body: RenderableType, border_style: str) -> RenderableType:
    return Group(
        Panel(
            body,
            title=_header(title),
            title_align="left",
            border_style=border_style,
            padding=(0, 2),
        ),
        Text(""),
    )


def _event_markdown(message: str) -> str:
    if message.startswith("Claude Code is using `"):
        return "- " + message
    if "permission denied" in message.lower():
        return f"> {message}"
    return message


def _claude_event_style(message: str) -> str:
    lowered = message.lower()
    if "permission denied" in lowered or "failed" in lowered:
        return ERROR_STYLE
    if "approval" in lowered or "interrupt" in lowered:
        return WARNING_STYLE
    return TEXT_STYLE


def _looks_like_diff(text: str) -> bool:
    lines = text.splitlines()
    return any(line.startswith(("diff --git", "@@ ", "+++ ", "--- ")) for line in lines) or (
        any(line.startswith("+") for line in lines)
        and any(line.startswith("-") for line in lines)
    )


def _looks_like_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return False
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _pretty_json(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, sort_keys=True)


def _looks_like_tool_message(message: str, tool: str) -> bool:
    return f"Claude Code is using `{tool}`" in message


def _extract_backticked_after(message: str, marker: str) -> str | None:
    if marker not in message:
        return None
    tail = message.split(marker, 1)[1]
    return tail.split("`", 1)[0] or None


def _strip_backticked_tail(message: str) -> str:
    return re.sub(r": `[^`]+`\.$", ".", message)


def _summary_activity(outputs: list[object]) -> dict[str, object]:
    for output in outputs:
        if not isinstance(output, dict):
            continue
        observed = output.get("observed_output")
        if not isinstance(observed, dict):
            continue
        activity = observed.get("activity")
        if isinstance(activity, dict):
            return activity
    return {}


def _summary_final_text(outputs: list[object]) -> str:
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]
