"""Claude Code attestation helper functions."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import ToolResultAttestation
from craik.runtime.store import LocalStore


def _put_claude_code_tool_attestations(
    store: LocalStore,
    *,
    task_id: str,
    run_id: str,
    case_file_id: str,
    receipt_id: str,
    events: list[dict[str, object]],
) -> list[ToolResultAttestation]:
    attestations: list[ToolResultAttestation] = []
    for index, event in enumerate(events, start=1):
        if event.get("kind") != "tool_use":
            continue
        tool = event.get("tool")
        if not isinstance(tool, str) or not tool:
            continue
        attestation = ToolResultAttestation(
            id=(
                f"attestation_{task_id.removeprefix('task_')}_"
                f"{run_id.removeprefix('run_')}_{index}_{_attestation_slug(tool)}"
            ),
            task_id=task_id,
            case_file_id=case_file_id,
            tool_name=f"claude_code.{tool}",
            tool_identity=str(event.get("target") or event.get("command") or tool),
            command=_claude_tool_command(event),
            observed_output_summary=str(
                event.get("message") or f"Claude Code used {tool}."
            ),
            trust_class="observed",
            status="attested",
            receipt_id=receipt_id,
            captured_at=datetime.now(UTC),
        )
        store.put_tool_result_attestation(attestation)
        attestations.append(attestation)
    return attestations


def _claude_tool_command(event: dict[str, object]) -> str | None:
    command = event.get("command")
    if isinstance(command, str) and command:
        return command
    target = event.get("target")
    if isinstance(target, str) and target:
        return target
    return None


def _attestation_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower() or "tool"


def _target_looks_like_file(target: str) -> bool:
    return "/" in target or "." in Path(target).name


def _claude_code_execution_prompt(compiled_prompt: str, objective: str) -> str:
    return (
        f"{compiled_prompt}\n\n"
        "## Claude Code Execution\n"
        "You are running inside the target repository through the local Claude Code CLI. "
        "Execute the task using the available Claude Code tools, including reading files, "
        "editing files, and running verification commands when appropriate. Do not only "
        "describe the work unless the active permission mode prevents edits.\n\n"
        f"Operator objective: {objective}\n\n"
        "When finished, return a concise summary with files changed, commands run, tests "
        "or checks performed, and any remaining risks."
    )


def _claude_model_arg(model: str) -> str | None:
    lowered = model.lower()
    if "opus" in lowered:
        return "opus"
    if "sonnet" in lowered:
        return "sonnet"
    if "haiku" in lowered:
        return "haiku"
    return None




