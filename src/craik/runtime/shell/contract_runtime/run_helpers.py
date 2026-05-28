"""Run command helpers for contract-native slash commands."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from craik.contracts.models import ProjectProfile, RunOutput
from craik.runtime.backend.claude_code_support import _clip_block
from craik.runtime.backend.session import (
    active_provider_and_model,
    execute_prompt,
    live_provider_enabled,
)
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.projects.project_registry import NotGitRepositoryError, ProjectRegistry
from craik.runtime.providers.model_providers import ModelProviderNotFoundError
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import ProjectNotFoundError, TaskNotFoundError


def run_command(*args: str, env: dict[str, str] | None = None) -> CommandResult:
    """Create and execute an audited task run from the TUI."""
    if not args:
        text = (
            "Usage: `/run <prompt>`\n\n"
            "Also available: `/run list`, `/run inspect <run-or-task-id>`."
        )
        return CommandResult(payload=text, shape="markdown", text=text, command_name="run")
    if args[0] == "list":
        return _run_list_result(env)
    if args[0] in {"inspect", "show"}:
        if len(args) < 2:
            text = "run inspect requires a run id or task id."
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        return _run_inspect_result(args[1], env)
    if args[0] == "timeline":
        if len(args) < 2:
            text = "run timeline requires a run id or task id."
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        return _run_timeline_result(args[1], env)
    try:
        backend, prompt_args = _parse_run_backend(args)
    except ValueError as error:
        text = str(error)
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    prompt = " ".join(prompt_args).strip()
    if not prompt:
        text = "run requires a prompt."
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    try:
        payload = _create_and_execute_run(prompt, env, backend=backend)
    except (
        ModelProviderNotFoundError,
        NotGitRepositoryError,
        ProjectNotFoundError,
        TaskNotFoundError,
        RuntimeError,
        ValueError,
    ) as error:
        text = str(error)
        return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
    label = "Audited run"
    text = _run_completion_text(label, payload)
    return CommandResult(payload=payload, shape="card", text=text, command_name="run")


def _create_and_execute_run(
    prompt: str,
    env: dict[str, str] | None,
    *,
    backend: Literal["auto", "provider", "claude-code"],
) -> dict[str, object]:
    return execute_prompt(
        prompt,
        env=env,
        source="tui",
        backend=backend,
        require_operator_approval=backend == "claude-code",
    ).payload_with_events()


def _parse_run_backend(
    args: tuple[str, ...],
) -> tuple[Literal["auto", "provider", "claude-code"], tuple[str, ...]]:
    backend: Literal["auto", "provider", "claude-code"] = "auto"
    remaining: list[str] = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == "--backend":
            if index + 1 >= len(args):
                raise ValueError("run --backend requires a value.")
            backend = _run_backend_value(args[index + 1])
            index += 2
            continue
        if argument.startswith("--backend="):
            backend = _run_backend_value(argument.split("=", 1)[1])
            index += 1
            continue
        remaining.append(argument)
        index += 1
    return backend, tuple(remaining)


def _run_backend_value(value: str) -> Literal["provider", "claude-code"]:
    if value == "provider":
        return "provider"
    if value == "claude-code":
        return "claude-code"
    raise ValueError("run backend must be `provider` or `claude-code`.")


def _run_completion_text(label: str, payload: dict[str, object]) -> str:
    run = payload["run"]
    handoff = payload["handoff"]
    receipt_ids = payload["receipt_ids"]
    if not isinstance(run, dict) or not isinstance(handoff, dict) or not isinstance(
        receipt_ids,
        list,
    ):
        raise ValueError("run payload is malformed")
    lines = [
        f"{label} `{run['id']}` completed with status "
        f"`{payload['status']}` for `{run['task_id']}`.",
        "",
        f"Handoff: `{handoff['id']}`",
        f"Receipts: {', '.join(str(item) for item in receipt_ids) or 'none'}",
    ]
    outputs = payload.get("run_outputs")
    run_outputs = outputs if isinstance(outputs, list) else []
    activity_text = _completion_activity_text(run_outputs)
    if activity_text:
        lines.extend(["", activity_text])
    final_text = _completion_final_text(run_outputs)
    if final_text:
        lines.extend(["", "Final output:", final_text])
    next_commands = payload.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(["", "Next:", *[f"- `{item}`" for item in next_commands if item]])
    text = "\n".join(lines)
    if payload.get("status") == "failed":
        failure = _failure_card_text(run_outputs)
        if failure:
            text = f"{text}\n\n{failure}"
    return text


def _completion_activity_text(outputs: list[object]) -> str:
    activity = _completion_activity(outputs)
    if not activity:
        return ""
    lines = ["Activity:"]
    tools = _string_list(activity.get("tools"))
    files = _string_list(activity.get("files"))
    commands = _string_list(activity.get("commands"))
    denials = activity.get("permission_denials")
    approvals = activity.get("runtime_approvals")
    if tools:
        lines.append(f"- Tools: {', '.join(f'`{item}`' for item in tools)}")
    if files:
        lines.append(f"- Files: {', '.join(f'`{item}`' for item in files)}")
    if commands:
        lines.append("- Commands:")
        lines.extend(f"  - `{item}`" for item in commands)
    if isinstance(approvals, list) and approvals:
        lines.append(f"- Runtime approvals observed: {len(approvals)}")
    if isinstance(denials, list) and denials:
        lines.append("- Permission denials:")
        for denial in denials[:5]:
            if isinstance(denial, dict):
                message = denial.get("message") or denial.get("reason") or denial.get("tool")
                if message:
                    lines.append(f"  - {message}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _completion_activity(outputs: list[object]) -> dict[str, object]:
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


def _completion_final_text(outputs: list[object]) -> str:
    for output in outputs:
        if not isinstance(output, dict):
            continue
        observed = output.get("observed_output")
        if not isinstance(observed, dict):
            continue
        text = observed.get("text")
        if isinstance(text, str) and text.strip():
            return _clip_block(text.strip(), limit=1200)
    return ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _failure_card_text(outputs: list[object]) -> str:
    diagnostics: list[str] = []
    last_event: str | None = None
    for output in outputs:
        if not isinstance(output, dict):
            continue
        raw_diagnostics = output.get("diagnostics")
        if isinstance(raw_diagnostics, list):
            diagnostics.extend(str(item) for item in raw_diagnostics if item)
        observed = output.get("observed_output")
        if isinstance(observed, dict):
            events = observed.get("progress_events")
            if isinstance(events, list) and events:
                last_event = str(events[-1])
    if not diagnostics and last_event is None:
        return ""
    lines = ["Failure details:"]
    if diagnostics:
        lines.append(f"- Cause: {diagnostics[0]}")
    if last_event:
        lines.append(f"- Last event: {last_event}")
    lines.append("- Next: inspect the run with `/run inspect <run-or-task-id>`.")
    return "\n".join(lines)


def _project_for_cwd(store: LocalStore) -> ProjectProfile:
    registry = ProjectRegistry(store)
    project = registry.add_project(Path.cwd())
    return project


def _active_provider_id(env: dict[str, str] | None) -> str:
    return _active_provider_and_model(env)[0]


def _active_provider_and_model(env: dict[str, str] | None) -> tuple[str, str | None]:
    return active_provider_and_model(env)


def _live_provider_enabled(env: dict[str, str] | None) -> bool:
    return live_provider_enabled(env)


def _title_from_prompt(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt).strip()
    if not normalized:
        return "TUI run"
    return normalized[:60].rstrip(" .,;:") or "TUI run"


def _run_list_result(env: dict[str, str] | None) -> CommandResult:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        payload = [run.model_dump(mode="json", by_alias=True) for run in store.list_task_runs()]
    finally:
        store.close()
    return CommandResult(payload=payload, shape="card_list", command_name="run")


def _run_inspect_result(run_or_task_id: str, env: dict[str, str] | None) -> CommandResult:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        run = next(
            (
                candidate
                for candidate in store.list_task_runs()
                if candidate.id == run_or_task_id or candidate.task_id == run_or_task_id
            ),
            None,
        )
        if run is None:
            text = f"unknown run or task: {run_or_task_id}"
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        outputs = [output for output in store.list_run_outputs() if output.run_id == run.id]
        receipts = [
            receipt
            for receipt in store.list_receipts()
            if receipt.id in run.receipt_ids
            or any(receipt.id in output.receipt_ids for output in outputs)
        ]
        payload = {
            "run": run.model_dump(mode="json", by_alias=True),
            "outputs": [output.model_dump(mode="json", by_alias=True) for output in outputs],
            "receipts": [receipt.model_dump(mode="json", by_alias=True) for receipt in receipts],
            "activity": _merged_activity(outputs),
        }
    finally:
        store.close()
    return CommandResult(payload=payload, shape="card", command_name="run")


def _run_timeline_result(run_or_task_id: str, env: dict[str, str] | None) -> CommandResult:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        run = next(
            (
                candidate
                for candidate in store.list_task_runs()
                if candidate.id == run_or_task_id or candidate.task_id == run_or_task_id
            ),
            None,
        )
        if run is None:
            text = f"unknown run or task: {run_or_task_id}"
            return CommandResult(payload=text, shape="markdown", text=text, exit_code=2)
        outputs = [output for output in store.list_run_outputs() if output.run_id == run.id]
        timeline: list[dict[str, object]] = [
            {
                "kind": "run",
                "message": f"Run {run.id} started.",
                "status": run.status,
                "phase": run.phase,
            }
        ]
        for output in outputs:
            observed = output.observed_output
            for event in observed.get("structured_events", []):
                if isinstance(event, dict):
                    timeline.append(
                        {
                            "kind": str(event.get("kind", "event")),
                            "message": str(event.get("message", "")),
                            "tool": event.get("tool"),
                            "target": event.get("target"),
                            "command": event.get("command"),
                        }
                    )
        timeline.append(
            {
                "kind": "run",
                "message": f"Run {run.id} ended with status {run.status}.",
                "status": run.status,
                "stop_reason": run.stop_reason,
            }
        )
    finally:
        store.close()
    return CommandResult(
        payload={"run_id": run.id, "task_id": run.task_id, "timeline": timeline},
        shape="card",
        command_name="run",
    )


def _merged_activity(outputs: list[RunOutput]) -> dict[str, object]:
    merged: dict[str, list[object]] = {
        "tools": [],
        "files": [],
        "commands": [],
        "permission_denials": [],
        "runtime_approvals": [],
    }
    for output in outputs:
        activity = output.observed_output.get("activity")
        if not isinstance(activity, dict):
            continue
        for key in merged:
            values = activity.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)
    return dict(merged)
