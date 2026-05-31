"""Gateway session orchestration for audited prompt execution."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from craik.contracts.models import RunOutput
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.provider_events import (
    provider_default_model,
)
from craik.runtime.modeling import ModelProfile, ModelSettingsStore
from craik.runtime.store import LocalStore

PromptSource = Literal["tui", "cli", "slash", "jsonl", "channel"]
BackendPreference = Literal["auto", "provider", "claude-code"]


class _LegacyRunAdapter(Protocol):
    """Adapters that bridge to a legacy ``execute_prompt`` branch (Task 2.4).

    ``select_adapter`` only ever resolves the dispatch identifiers used here
    (``anthropic-cli`` / ``anthropic-api``) to ``AnthropicCLI`` / ``AnthropicAPI``,
    both of which implement ``_legacy_run``. This Protocol narrows the dispatch
    site without widening the public ``Adapter`` protocol with a legacy hook.
    """

    def _legacy_run(
        self,
        ctx: object,
        *,
        events: list[BackendEvent],
        source: str,
        env: dict[str, str] | None,
    ) -> BackendPromptResult: ...


@dataclass(frozen=True)
class BackendPromptResult:
    """Audited prompt execution result returned to Gateway clients."""

    payload: dict[str, object]
    events: list[BackendEvent] = field(default_factory=list)

    def payload_with_events(self) -> dict[str, object]:
        """Return the legacy payload plus normalized Gateway events."""
        return {
            **self.payload,
            "gateway_events": [event.as_dict() for event in self.events],
        }


def execute_prompt(
    prompt: str,
    *,
    env: dict[str, str] | None = None,
    source: PromptSource = "tui",
    backend: BackendPreference = "auto",
    require_operator_approval: bool | None = None,
    stream: Callable[[BackendEvent], None] | None = None,
) -> BackendPromptResult:
    """Create and execute one audited provider-backed prompt run."""
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise ValueError("prompt is required")
    events: list[BackendEvent] = []

    def emit(event: BackendEvent) -> None:
        events.append(event)
        if stream is not None:
            stream(event)

    emit(
        BackendEvent(
            type="prompt.submitted",
            data={"source": source, "prompt_preview": _clip(normalized_prompt)},
        )
    )
    # `approval_required`'s default must reproduce today's `backend == "claude-code"`
    # rule EXACTLY -- computed here, before dispatch, so the value handed to the
    # claude path is identical. (The provider path ignores it.)
    approval_required = (
        require_operator_approval
        if require_operator_approval is not None
        else backend == "claude-code"
    )
    # Map the legacy `BackendPreference` to a canonical adapter id. "auto" stays
    # "auto" and is resolved by `select_adapter` via the SAME anthropic-marker
    # rule the old branch used, so routing is preserved:
    #   claude-code      -> anthropic-cli (claude path)
    #   auto + marker    -> anthropic-cli (claude path)  [resolved in select_adapter]
    #   auto, no marker  -> anthropic-api (provider path)
    #   provider         -> anthropic-api (provider path)
    identifier = {"claude-code": "anthropic-cli", "provider": "anthropic-api"}.get(backend, backend)
    from craik.runtime.backend.adapters.base import RunContext
    from craik.runtime.backend.adapters.registry import select_adapter

    adapter = cast(_LegacyRunAdapter, select_adapter(identifier, env))
    ctx = RunContext(
        prompt=normalized_prompt,
        # `RunContext.env` is non-optional, so coerce None -> {} for protocol
        # correctness. The legacy helpers do NOT read from `ctx.env`: the
        # ORIGINAL `env` (possibly None) is threaded separately via the `env=`
        # argument below so behavior stays byte-identical (e.g.
        # `LocalStore.from_env(None)` vs `from_env({})`).
        env=env or {},
        emit=emit,
        # Legacy paths do not gate via `decide`; a placeholder satisfies the
        # protocol without affecting either legacy branch.
        decide=lambda _request: "allow",
        require_operator_approval=approval_required,
    )
    return adapter._legacy_run(ctx, events=events, source=source, env=env)


def _persist_gateway_event_history(
    payload: dict[str, object],
    events: list[BackendEvent],
    *,
    store: LocalStore | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Persist redacted Gateway event history as a run output artifact."""
    run = payload.get("run")
    task = payload.get("task")
    if not isinstance(run, dict) or not isinstance(task, dict):
        return
    run_id = run.get("id")
    task_id = task.get("id") or run.get("task_id")
    if not isinstance(run_id, str) or not isinstance(task_id, str):
        return
    raw_receipt_ids = payload.get("receipt_ids")
    receipt_ids = (
        [receipt_id for receipt_id in raw_receipt_ids if isinstance(receipt_id, str)]
        if isinstance(raw_receipt_ids, list)
        else []
    )
    output = RunOutput(
        id=f"run_output_{run_id}_gateway_events",
        run_id=run_id,
        step_result_id="gateway_event_history",
        task_id=task_id,
        phase="observe",
        summary=f"Gateway recorded {len(events)} event(s) for audited prompt run.",
        observed_output={
            "source": "craik.gateway",
            "event_count": len(events),
            "events": [event.as_dict() for event in events],
        },
        diagnostics=[],
        receipt_ids=receipt_ids,
        artifacts=[],
        redacted=True,
        created_at=datetime.now(UTC),
    )
    if store is not None:
        store.put_run_output(output)
        return
    owned_store = LocalStore.from_env(env)
    try:
        owned_store.initialize()
        owned_store.put_run_output(output)
    finally:
        owned_store.close()


def active_provider_and_model(env: dict[str, str] | None) -> tuple[str, str | None]:
    """Return the active provider id and model from persisted model settings."""
    settings = ModelSettingsStore.from_env(env).load()
    active_profile = settings.active_profile
    if active_profile is not None:
        return active_profile.provider_id, active_profile.model
    active_model = settings.active_model
    if not active_model:
        return "provider_openai", None
    provider_name = active_model.split("/", 1)[0]
    model = active_model.split("/", 1)[1] if "/" in active_model else None
    provider_id = {
        "anthropic": "provider_anthropic",
        "claude": "provider_anthropic",
        "openai": "provider_openai",
        "gemini": "provider_gemini",
        "google": "provider_gemini",
        "openai-compatible": "provider_local_openai_compatible",
        "local": "provider_local_openai_compatible",
        "ollama": "provider_local_ollama",
        "lm-studio": "provider_local_lm_studio",
        "vllm": "provider_local_vllm",
    }.get(provider_name, provider_name)
    return provider_id, model or provider_default_model(provider_id)


def active_model_profile(env: dict[str, str] | None) -> ModelProfile | None:
    """Return the active persisted model profile, if present."""
    return ModelSettingsStore.from_env(env).load().active_profile


def live_provider_enabled(env: dict[str, str] | None) -> bool:
    """Return whether selected provider execution should use live transport."""
    values = os.environ if env is None else env
    if values.get("CRAIK_LIVE") == "0":
        return False
    if values.get("CRAIK_FIXTURE") == "1":
        return False
    return ModelSettingsStore.from_env(env).load().active_model is not None


def _title_from_prompt(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt).strip()
    if not normalized:
        return "TUI run"
    return normalized[:60].rstrip(" .,;:") or "TUI run"


def _clip(value: str, limit: int = 240) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}..."


def _anthropic_marker_uses_claude_code(env: dict[str, str] | None) -> bool:
    from craik.runtime.backend.claude_code import (
        anthropic_uses_claude_cli_marker,
    )

    return anthropic_uses_claude_cli_marker(env)


def _execute_claude_code_prompt(
    prompt: str,
    *,
    env: dict[str, str] | None,
    stream: Callable[[BackendEvent], None] | None = None,
    require_operator_approval: bool = False,
) -> dict[str, object]:
    from craik.runtime.backend.claude_code import (
        claude_code_progress,
        execute_claude_code_run,
    )

    def emit_progress(message: str) -> None:
        if stream is not None:
            stream(BackendEvent(type="run.progress", data={"message": message}))

    def emit_claude_event(event: dict[str, object]) -> None:
        if stream is not None:
            stream(claude_structured_event_to_backend_event(event))

    with claude_code_progress(emit_progress, event_callback=emit_claude_event):
        return execute_claude_code_run(
            prompt,
            env,
            require_operator_approval=require_operator_approval,
        )


def claude_structured_event_to_backend_event(event: dict[str, object]) -> BackendEvent:
    """Map one parsed Claude Code stream event to the Gateway event contract."""
    kind = str(event.get("kind") or "event")
    message = str(event.get("message") or "").strip()
    data = {
        "backend": "claude-code",
        "kind": kind,
        **_json_safe_event_data(event),
    }
    if message:
        data["message"] = message
    if kind == "tool_use":
        return BackendEvent(type="tool.used", data=data)
    if kind == "file_change":
        return BackendEvent(type="file.changed", data=data)
    if kind == "approval_request":
        return BackendEvent(type="approval.requested", data=data)
    if kind == "permission_denial":
        return BackendEvent(type="approval.denied", data=data)
    if kind in {"assistant_text", "result", "output", "system", "error", "event", "tool_result"}:
        return BackendEvent(type="run.event", data=data)
    return BackendEvent(type="run.event", data=data)


def _json_safe_event_data(event: dict[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in event.items():
        if key == "message":
            continue
        safe[key] = _json_safe_value(value)
    return safe


def _json_safe_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    return str(value)
